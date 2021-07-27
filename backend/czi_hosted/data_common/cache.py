from abc import ABC, abstractmethod
import threading
import time


from backend.common.errors import DatasetAccessError
from contextlib import contextmanager

from backend.czi_hosted.data_common.rwlock import RWLock


class CacheItem(ABC):
    """This class provides an abstract base class for caching information.  The first time information is accessed,
    it is located and cached.  Later accesses use the cached version.   It may also be deleted by the
    DataCacheManager to make room.  While data is actively being used (during the lifetime of an api request),
    a reader lock is locked.  During that time, the data cannot be removed or updated."""

    def __init__(self, loader):
        self.loader = loader
        self.data_lock = RWLock()
        self.data_adaptor = None

    def acquire_existing(self):
        """If the data exists, take a read lock and return it, else return None"""
        self.data_lock.r_acquire()
        if self.data_adaptor:
            return self.data_adaptor

        self.data_lock.r_release()
        return None

    def acquire_and_open(self, app_config, dataset_config=None):
        """returns the data_adaptor if cached.  opens the data_adaptor if not.
        In either case, the a reader lock is taken.  Must call release when
        the data_adaptor is no longer needed"""
        self.data_lock.r_acquire()
        if self.data_adaptor:
            return self.data_adaptor
        self.data_lock.r_release()

        self.data_lock.w_acquire()
        # the data may have been loaded while waiting on the lock
        if not self.data_adaptor:
            try:
                self.loader.pre_load_validation()
                self.data_adaptor = self.loader.open(app_config, dataset_config)
            except Exception as e:
                # necessary to hold the reader lock after an exception, since
                # the release will occur when the context exits.
                self.data_lock.w_demote()
                raise DatasetAccessError(str(e))

        # demote the write lock to a read lock.
        self.data_lock.w_demote()
        return self.data_adaptor

    def release(self):
        """Release the reader lock"""
        self.data_lock.r_release()

    def delete(self):
        """Clear resources used by this cache item"""
        with self.data_lock.w_locked():
            if self.data_adaptor:
                self.data_adaptor.cleanup()
                self.data_adaptor = None

    def attempt_delete(self):
        """Delete, but only if the write lock can be immediately locked.  Return True if the delete happened"""
        if self.data_lock.w_acquire_non_blocking():
            if self.data_adaptor:
                try:
                    self.data_adaptor.cleanup()
                    self.data_adaptor = None
                except Exception:
                    # catch all exceptions to ensure the lock is released
                    pass

                self.data_lock.w_release()
                return True
        else:
            return False


class CacheItemInfo(object):
    def __init__(self, cache_item, timestamp):
        # The DataCacheItem in the cache
        self.cache_item = cache_item
        # The last time the cache_item was accessed
        self.last_access = timestamp
        # The number of times the cache_item was accessed (used for testing)
        self.num_access = 1


class CacheManager(ABC):
    """An abstract base class to manage the cached data. This is intended to be used as a context manager
    for handling api requests.  When the context is created, the data_adaptor is either loaded or
    retrieved from a cache.  In either case, the reader lock is taken during this time, and release
    when the context ends.  This class currently implements a simple least recently used cache,
    which can delete data from the cache to make room for a new one.

    This is the intended usage pattern:

           cache_manager = DataCacheManager(max_cached=..., timelimmit_s = ...)
           with cache_manager.data_adaptor(location, app_config) as data_adaptor:
               # use the data_adaptor for some operation
    """

    # FIXME:   If the number of active datasets exceeds the max_cached, then each request could
    # lead to a dataset being deleted and a new only being opened: the cache will get thrashed.
    # In this case, we may need to send back a 503 (Server Unavailable), or some other error message.

    # NOTE:  If the actual dataset is changed.  E.g. a new set of datafiles replaces an existing set,
    # then the cache will not react to this, however once the cache time limit is reached, the dataset
    # will automatically be refreshed.

    def __init__(self, max_cached, timelimit_s=None):
        # key is tuple(url_dataroot, location), value is a DataCacheInfo object
        self.data = {}

        # lock to protect the datasets
        self.lock = threading.Lock()

        #  The number of datasets to cache.  When max_cached is reached, the least recently used
        #  cache is replaced with the newly requested one.
        #  TODO:  This is very simple.  This can be improved by taking into account how much space is actually
        #         taken by each dataset, instead of arbitrarily picking a max datasets to cache.
        self.max_cached = max_cached

        # items are automatically removed from the cache once this time limit is reached
        self.timelimit_s = timelimit_s

    @contextmanager
    def data_adaptor(self, url_dataroot, location, app_config, dataset=None):
        # create a loader for to this location if it does not already exist

        delete_adaptor = None
        data_adaptor = None
        cache_item = None

        key = (url_dataroot, location)
        with self.lock:
            self.evict_old_data()
            info = self.data.get(key)
            if info is not None:
                info.last_access = time.time()
                info.num_access += 1
                self.data[key] = info
                data_adaptor = info.cache_item.acquire_existing()
                cache_item = info.cache_item

            if data_adaptor is None:
                # if app_config.server_config.data_locator__api_base and dataset:
                #     if url_dataroot == "e":  # only pull dataset identification information from the portal for /e/ route
                #         dataset_identifiers = self.get_dataset_location_from_data_portal(url_dataroot, app_config, dataset)
                #         if dataset_identifiers and dataset_identifiers['s3_uri'] and dataset_identifiers["tombstoned"] == 'False':
                #             location = dataset_identifiers["s3_uri"]
                while True:
                    if len(self.data) < self.max_cached:
                        break

                    items = list(self.data.items())
                    items = sorted(items, key=lambda x: x[1].last_access)
                    # close the least recently used loader
                    oldest = items[0]
                    oldest_cache = oldest[1].cache_item
                    oldest_key = oldest[0]
                    del self.data[oldest_key]
                    delete_adaptor = oldest_cache
                loader = MatrixDataLoader(location, app_config=app_config)
                cache_item = MatrixDataCacheItem(loader)
                item = CacheItemInfo(cache_item, time.time())
                self.data[key] = item

        try:
            assert cache_item
            if delete_adaptor:
                delete_adaptor.delete()
            if data_adaptor is None:
                dataset_config = app_config.get_dataset_config(url_dataroot)
                data_adaptor = cache_item.acquire_and_open(app_config, dataset_config)
            yield data_adaptor
        except DatasetAccessError:
            cache_item.release()
            with self.lock:
                del self.data[key]
                cache_item.delete()
            cache_item = None
            raise

        finally:
            if cache_item:
                cache_item.release()


    def evict_old_data(self):
        # must be called with the lock held
        if self.timelimit_s is None:
            return

        now = time.time()
        to_del = []
        for key, info in self.data.items():
            if (now - info.last_access) > self.timelimit_s:
                # remove the data_cache when if it has been in the cache too long
                to_del.append((key, info))

        for key, info in to_del:
            # try and get the write_lock for the dataset.
            # if this returns false, it means the dataset is being used, and should
            # not be removed.
            if info.cache_item.attempt_delete():
                del self.data[key]


class DataLoader(ABC):
    @abstractmethod
    def pre_load_validation(self):
        pass

    @abstractmethod
    def open(self):
        # returns the data adaptor of the data item
        pass

    @abstractmethod
    def cleanup(self):
        pass

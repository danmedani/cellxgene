import json
from abc import ABC, abstractmethod
import threading
import time

import requests

from contextlib import contextmanager

from backend.czi_hosted.data_common.cache import CacheItem, CacheManager, CacheItemInfo, DataLoader
from backend.czi_hosted.data_common.rwlock import RWLock


class DatasetLocationCacheItem(CacheItem):
    """This class provides an abstract base class for caching information.  The first time information is accessed,
    it is located and cached.  Later accesses use the cached version.   It may also be deleted by the
    DataCacheManager to make room.  While data is actively being used (during the lifetime of a api request),
    a reader lock is locked.  During that time, the data cannot be removed or updated."""

    def __init__(self, loader):
        self.data_loader = loader
        self.data_lock = RWLock()
        self.data_adaptor = None


    @abstractmethod
    def acquire_and_open(self, app_config, dataset_config=None, data_loading_function=None):
        pass



class DatasetLocationCacheManager(CacheManager):
    @contextmanager
    def data_adaptor(self, url_dataroot, location, app_config, dataset=None):
        # load data for to this location if it does not already exist
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
                if app_config.server_config.data_locator__api_base and dataset:
                    if url_dataroot == "e":  # only pull dataset identification information from the portal for /e/ route
                        dataset_identifiers = self.get_dataset_location_from_data_portal(url_dataroot, app_config,
                                                                                         dataset)
                        if dataset_identifiers and dataset_identifiers['s3_uri'] and dataset_identifiers[
                            "tombstoned"] == 'False':
                            location = dataset_identifiers["s3_uri"]
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
                loader = DatasetLocationDataLoader(location, app_config=app_config)
                cache_item = DatasetLocationCacheItem(loader)
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



class DatasetLocationDataLoader(DataLoader):
    def __init__(self, dataset_url):
        pass
    def pre_load_validation(self):
        pass

    def open(self):
        pass

    def get_dataset_location_from_data_portal(self, url_dataroot, app_config, dataset):
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        curr_url = f"{app_config.server_config.get_web_base_url()}/{url_dataroot}/{dataset}"
        try:
            response = requests.get(
                url=f"http://{app_config.server_config.data_locator__api_base}/datasets/meta?url={curr_url}",
                headers=headers
            )
            if response.status_code == 200:
                dataset_identifiers = json.loads(response.body)
                return dataset_identifiers
        except Exception as e:
            return None


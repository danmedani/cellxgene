import os
from os.path import splitext, isdir

from backend.czi_hosted.common.annotations.annotations import Annotations
from backend.czi_hosted.common.annotations.hosted_tiledb import AnnotationsHostedTileDB
from backend.czi_hosted.common.annotations.local_file_csv import AnnotationsLocalFile
from backend.czi_hosted.common.config.base_config import BaseConfig
from backend.common.errors import ConfigurationError
from backend.czi_hosted.db.db_utils import DbUtils


class DatasetConfig(BaseConfig):
    """Manages the config attribute associated with a dataset."""

    def __init__(self, tag, app_config, default_config):
        super().__init__(app_config, default_config)
        self.tag = tag
        try:
            self.app__scripts = default_config["app"]["scripts"]
            self.app__inline_scripts = default_config["app"]["inline_scripts"]
            self.app__about_legal_tos = default_config["app"]["about_legal_tos"]
            self.app__about_legal_privacy = default_config["app"]["about_legal_privacy"]
            self.app__authentication_enable = default_config["app"]["authentication_enable"]

            self.presentation__max_categories = default_config["presentation"]["max_categories"]
            self.presentation__custom_colors = default_config["presentation"]["custom_colors"]

            self.user_annotations__enable = default_config["user_annotations"]["enable"]
            self.user_annotations__type = default_config["user_annotations"]["type"]
            self.user_annotations__local_file_csv__directory = default_config["user_annotations"]["local_file_csv"][
                "directory"
            ]
            self.user_annotations__local_file_csv__file = default_config["user_annotations"]["local_file_csv"]["file"]
            self.user_annotations__hosted_tiledb_array__db_uri = default_config["user_annotations"][
                "hosted_tiledb_array"
            ]["db_uri"]
            self.user_annotations__hosted_tiledb_array__hosted_file_directory = default_config["user_annotations"][
                "hosted_tiledb_array"
            ]["hosted_file_directory"]

            self.embeddings__names = default_config["embeddings"]["names"]

            self.diffexp__enable = default_config["diffexp"]["enable"]
            self.diffexp__lfc_cutoff = default_config["diffexp"]["lfc_cutoff"]
            self.diffexp__top_n = default_config["diffexp"]["top_n"]

            self.X_approximate_distribution = default_config["X_approximate_distribution"]

        except KeyError as e:
            raise ConfigurationError(f"Unexpected config: {str(e)}")

        # Create the default annotation, which supports gene set reading without
        # further configuration. Depending on configuration options, `complete_config`
        # may create a more specialized annotation object and replace this default.
        self.user_annotations = Annotations()

    def complete_config(self, context):
        self.handle_app()
        self.handle_presentation()
        self.handle_user_annotations(context)
        self.handle_embeddings()
        self.handle_diffexp(context)
        self.handle_X_approximate_distribution()

    def handle_app(self):
        self.validate_correct_type_of_configuration_attribute("app__scripts", list)
        self.validate_correct_type_of_configuration_attribute("app__inline_scripts", list)
        self.validate_correct_type_of_configuration_attribute("app__about_legal_tos", (type(None), str))
        self.validate_correct_type_of_configuration_attribute("app__about_legal_privacy", (type(None), str))
        self.validate_correct_type_of_configuration_attribute("app__authentication_enable", bool)

        # scripts can be string (filename) or dict (attributes). Convert string to dict.
        scripts = []
        for script in self.app__scripts:
            try:
                if isinstance(script, str):
                    scripts.append({"src": script})
                elif isinstance(script, dict) and isinstance(script["src"], str):
                    scripts.append(script)
                else:
                    raise Exception
            except Exception as e:
                raise ConfigurationError(f"Scripts must be string or a dict containing an src key: {e}")

        self.app__scripts = scripts

    def handle_presentation(self):
        self.validate_correct_type_of_configuration_attribute("presentation__max_categories", int)
        self.validate_correct_type_of_configuration_attribute("presentation__custom_colors", bool)

    def handle_user_annotations(self, context):
        self.validate_correct_type_of_configuration_attribute("user_annotations__enable", bool)
        self.validate_correct_type_of_configuration_attribute("user_annotations__type", str)
        self.validate_correct_type_of_configuration_attribute(
            "user_annotations__local_file_csv__directory", (type(None), str)
        )
        self.validate_correct_type_of_configuration_attribute(
            "user_annotations__local_file_csv__file", (type(None), str)
        )
        self.validate_correct_type_of_configuration_attribute(
            "user_annotations__hosted_tiledb_array__db_uri", (type(None), str)
        )
        self.validate_correct_type_of_configuration_attribute(
            "user_annotations__hosted_tiledb_array__hosted_file_directory", (type(None), str)
        )
        if self.user_annotations__enable:
            server_config = self.app_config.server_config
            if not self.app__authentication_enable:
                raise ConfigurationError("user annotations requires authentication to be enabled")
            if not server_config.auth.is_valid_authentication_type():
                auth_type = server_config.authentication__type
                raise ConfigurationError(f"authentication method {auth_type} is not compatible with user annotations")

            if self.user_annotations__type == "local_file_csv":
                self.handle_local_file_csv_annotations()
            elif self.user_annotations__type == "hosted_tiledb_array":
                self.handle_hosted_tiledb_annotations()
            else:
                raise ConfigurationError('The only annotation type support is "local_file_csv" or "hosted_tiledb_array')
        else:
            self.check_annotation_config_vars_not_set(context)

    def handle_local_file_csv_annotations(self):
        dirname = self.user_annotations__local_file_csv__directory
        filename = self.user_annotations__local_file_csv__file
        if filename is not None and dirname is not None:
            raise ConfigurationError("'annotations-file' and 'annotations-dir' may not be used together.")

        if filename is not None:
            lf_name, lf_ext = splitext(filename)
            if lf_ext and lf_ext != ".csv":
                raise ConfigurationError(f"annotation file type must be .csv: {filename}")

        if dirname is not None and not isdir(dirname):
            try:
                os.mkdir(dirname)
            except OSError:
                raise ConfigurationError("Unable to create directory specified by --annotations-dir")

        anno_config = {
            "user-annotations": self.user_annotations__enable,
            "genesets-save": False,
        }
        self.user_annotations = AnnotationsLocalFile(anno_config, dirname, filename)

        # if the user has specified a fixed label file, go ahead and validate it
        # so that we can remove errors early in the process.
        server_config = self.app_config.server_config
        if server_config.single_dataset__datapath and self.user_annotations__local_file_csv__file:
            with server_config.matrix_data_cache_manager.data_adaptor(
                self.tag, server_config.single_dataset__datapath, self.app_config
            ) as data_adaptor:
                data_adaptor.check_new_labels(self.user_annotations.read_labels(data_adaptor))

    def handle_hosted_tiledb_annotations(self):
        self.validate_correct_type_of_configuration_attribute("user_annotations__hosted_tiledb_array__db_uri", str)
        self.validate_correct_type_of_configuration_attribute(
            "user_annotations__hosted_tiledb_array__hosted_file_directory", str
        )
        anno_config = {
            "user-annotations": self.user_annotations__enable,
            "genesets-save": False,
        }
        self.user_annotations = AnnotationsHostedTileDB(
            anno_config,
            directory_path=self.user_annotations__hosted_tiledb_array__hosted_file_directory,
            db=DbUtils(self.user_annotations__hosted_tiledb_array__db_uri),
        )

    def check_annotation_config_vars_not_set(self, context):
        if self.user_annotations__type is not None:
            dirname = self.user_annotations__local_file_csv__directory
            filename = self.user_annotations__local_file_csv__file
            db_uri = self.user_annotations__hosted_tiledb_array__db_uri
            hosted_file_dirname = self.user_annotations__hosted_tiledb_array__hosted_file_directory
            if filename is not None:
                context["messagefn"]("Warning: --annotations-file ignored as annotations are disabled.")
            if dirname is not None:
                context["messagefn"]("Warning: --annotations-dir ignored as annotations are disabled.")
            if db_uri is not None:
                context["messagefn"]("Warning: db_uri ignored as annotations are disabled.")
            if hosted_file_dirname is not None:
                context["messagefn"](
                    "Warning: hosted_file_directory for hosted_tiledb_array ignored as annotations are disabled."
                )

    def handle_embeddings(self):
        self.validate_correct_type_of_configuration_attribute("embeddings__names", list)

    def handle_diffexp(self, context):
        self.validate_correct_type_of_configuration_attribute("diffexp__enable", bool)
        self.validate_correct_type_of_configuration_attribute("diffexp__lfc_cutoff", float)
        self.validate_correct_type_of_configuration_attribute("diffexp__top_n", int)

        server_config = self.app_config.server_config
        if server_config.single_dataset__datapath:
            with server_config.matrix_data_cache_manager.data_adaptor(
                self.tag, server_config.single_dataset__datapath, self.app_config
            ) as data_adaptor:
                if self.diffexp__enable and data_adaptor.parameters.get("diffexp_may_be_slow", False):
                    context["messagefn"](
                        "CAUTION: due to the size of your dataset, "
                        "running differential expression may take longer or fail."
                    )

    def handle_X_approximate_distribution(self):
        self.validate_correct_type_of_configuration_attribute("X_approximate_distribution", str)
        if self.X_approximate_distribution not in ["normal", "count"]:
            raise ConfigurationError(
                "X_approximate_distribution has unknown value -- must be 'normal' or 'count'."
            )

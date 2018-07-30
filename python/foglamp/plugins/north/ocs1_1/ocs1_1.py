# -*- coding: utf-8 -*-

# FOGLAMP_BEGIN
# See: http://foglamp.readthedocs.io/
# FOGLAMP_END

""" The OCS North is a plugin output formatter for the FogLAMP appliance.
    It is loaded by the send process (see The FogLAMP Sending Process) and runs in the context of the send process,
    to send the reading data to OSIsoft OCS (OSIsoft Cloud Services) using the OSIsoft OMF format.
    PICROMF = PI Connector Relay OMF
"""

import aiohttp
import copy
import ast
import time
import json
import logging
import foglamp.plugins.north.common.common as plugin_common
import foglamp.plugins.north.common.exceptions as plugin_exceptions
from foglamp.common import logger
from foglamp.common.storage_client import payload_builder
from foglamp.common.storage_client.exceptions import StorageServerError

import foglamp.plugins.north.omf1_1.omf1_1 as omf

__author__ = "Stefano Simonelli, Amarendra K Sinha"
__copyright__ = "Copyright (c) 2017 OSIsoft, LLC"
__license__ = "Apache 2.0"
__version__ = "${VERSION}"


_logger = None
_MODULE_NAME = "ocs_north"
_log_debug_level = 0
_log_performance = False
_stream_id = None
_destination_id = None
_config_omf_types = {}
_config = {}
_recreate_omf_objects = True
_CONFIG_CATEGORY_DESCRIPTION = 'Configuration of OCS North plugin'
# The parameters used for the interaction with OCS are :
#    producerToken                      - It allows to ingest data into OCS using OMF.
#    tenant_id / client_id / client_id  - They are used for the authentication and interaction with the OCS API,
#                                         they are associated to the specific OCS account.
#    namespace                          - Specifies the OCS namespace where the information are stored,
#                                         it is used for the interaction with the OCS API.
#
_CONFIG_DEFAULT_OMF = {
    'plugin': {
        'description': 'OCS North Plugin',
        'type': 'string',
        'default': 'ocs'
    },
    "URL": {
        "description": "The URL of OCS (OSIsoft Cloud Services) ",
        "type": "string",
        "default": "https://dat-a.osisoft.com/api/omf"
    },
    "producerToken": {
        "description": "The producer token used to authenticate as a valid publisher and "
                       "required to ingest data into OCS using OMF.",
        "type": "string",
        "default": "1/76aceb58cfad4cb788cf584a3ba0a8c7/8b13cb6b18db4c508e3ad2bfc4221653/4be9ded8-c6a6-44ac-8e1a-9db44e58fa49/65238084000/qQLjZMvRN95vBAAz2uaRhGy1R55a4D5bOaWjG0OCXbY%3D"
    },
    "namespace": {
        "description": "Specifies the OCS namespace where the information are stored and "
                       "it is used for the interaction with the OCS API.",
        "type": "string",
        "default": "ocs_namespace_0001"
    },
    "tenant_id": {
      "description": "Tenant id associated to the specific OCS account.",
      "type": "string",
      "default": "ocs_tenant_id"
    },
    "client_id": {
      "description": "Client id associated to the specific OCS account, "
                     "it is used to authenticate the source for using the OCS API.",
      "type": "string",
      "default": "ocs_client_id"
    },
    "client_secret": {
      "description": "Client secret associated to the specific OCS account, "
                     "it is used to authenticate the source for using the OCS API.",
      "type": "string",
      "default": "ocs_client_secret"
    },
    "OMFMaxRetry": {
        "description": "Max number of retries for the communication with the OMF PI Connector Relay",
        "type": "integer",
        "default": "5"
    },
    "OMFRetrySleepTime": {
        "description": "Seconds between each retry for the communication with the OMF PI Connector Relay",
        "type": "integer",
        "default": "1"
    },
    "OMFHttpTimeout": {
        "description": "Timeout in seconds for the HTTP operations with the OMF PI Connector Relay",
        "type": "integer",
        "default": "30"
    },
    "StaticData": {
        "description": "Static data to include in each sensor reading sent to OMF.",
        "type": "JSON",
        "default": json.dumps(
            {
                "Location": "Palo Alto",
                "Company": "Dianomic"
            }
        )
    },
    "applyFilter": {
        "description": "Whether to apply filter before processing the data",
        "type": "boolean",
        "default": "False"
    },
    "filterRule": {
        "description": "JQ formatted filter to apply (applicable if applyFilter is True)",
        "type": "string",
        "default": ".[]"
    },
    "formatNumber": {
        "description": "OMF format property to apply to the type Number",
        "type": "string",
        "default": "float64"
    },
    "formatInteger": {
        "description": "OMF format property to apply to the type Integer",
        "type": "string",
        "default": "int32"
    }
}
_CONFIG_CATEGORY_OMF_TYPES_NAME = 'OCS_TYPES'
_CONFIG_CATEGORY_OMF_TYPES_DESCRIPTION = 'Configuration of OCS types'
_CONFIG_DEFAULT_OMF_TYPES = omf._CONFIG_DEFAULT_OMF_TYPES
_OMF_PREFIX_MEASUREMENT = "measurement_"
_OMF_SUFFIX_TYPENAME = "_typename"

def plugin_info():
    """ Returns information about the plugin."""
    return {
        'name': "OCS North",
        'version': "1.0.0",
        'type': "north",
        'interface': "1.0",
        'config': _CONFIG_DEFAULT_OMF
    }


def plugin_init(data):
    """ Initializes the OMF plugin for the sending of blocks of readings to the PI Connector."""

    # No need to proceed further if producerToken is missing or is invalid
    try:
        assert data['producerToken'] != ""
    except KeyError:
        raise ValueError("the producerToken must be defined, use the FogLAMP API to set a proper value.")
    except AssertionError:
        raise ValueError("the producerToken cannot be an empty string, use the FogLAMP API to set a proper value.")

    global _config
    global _config_omf_types
    global _logger
    global _recreate_omf_objects
    global _log_debug_level, _log_performance, _stream_id, _destination_id
    global _OMF_PREFIX_MEASUREMENT, _OMF_SUFFIX_TYPENAME

    _OMF_PREFIX_MEASUREMENT = _OMF_PREFIX_MEASUREMENT + data['source']['value'] + "_"
    _OMF_SUFFIX_TYPENAME = _OMF_SUFFIX_TYPENAME + "_" + data['source']['value']

    _log_debug_level = data['debug_level']
    _log_performance = data['log_performance']
    _stream_id = data['stream_id']
    _destination_id = data['destination_id']

    logger_name = _MODULE_NAME + "_" + str(_stream_id)
    _logger = logger.setup(logger_name, level=logging.INFO if _log_debug_level in [0, 1, None] else logging.DEBUG)

    _config['_CONFIG_CATEGORY_NAME'] = data['_CONFIG_CATEGORY_NAME']
    _config['URL'] = data['URL']['value']
    _config['producerToken'] = data['producerToken']['value']
    _config['OMFMaxRetry'] = int(data['OMFMaxRetry']['value'])
    _config['OMFRetrySleepTime'] = int(data['OMFRetrySleepTime']['value'])
    _config['OMFHttpTimeout'] = int(data['OMFHttpTimeout']['value'])
    _config['StaticData'] = ast.literal_eval(data['StaticData']['value'])
    _config['formatNumber'] = data['formatNumber']['value']
    _config['formatInteger'] = data['formatInteger']['value']
    _config['sending_process_instance'] = data['sending_process_instance']

    _config_omf_types = _config['sending_process_instance']._fetch_configuration(
                                  cat_name=_CONFIG_CATEGORY_OMF_TYPES_NAME,
                                  cat_desc=_CONFIG_CATEGORY_OMF_TYPES_DESCRIPTION,
                                  cat_config=_CONFIG_DEFAULT_OMF_TYPES,
                                  cat_keep_original=True)
    try:
        assert _config_omf_types['type-id'] != ""
    except KeyError:
        raise ValueError("the type-id must be defined, use the FogLAMP API to set a proper value.")
    except AssertionError:
        raise ValueError("the type-id cannot be an empty string, use the FogLAMP API to set a proper value.")

    # TODO: refine below
    for item in _config_omf_types:
        if _config_omf_types[item]['type'] == 'JSON':
            # The conversion from a dict to str changes the case and it should be fixed before the conversion
            value = _config_omf_types[item]['value'].replace("true", "True")
            new_value = ast.literal_eval(value)
            _config_omf_types[item]['value'] = new_value
    _recreate_omf_objects = True

    return _config


async def plugin_send(data, raw_data, stream_id):
    """ Translates and sends to the destination system the data provided by the Sending Process
    Args:
        data: plugin_handle from sending_process
        raw_data  : Data to send as retrieved from the storage layer
        stream_id
    Returns:
        data_to_send : True, data successfully sent to the destination system
        new_position : Last row_id already sent
        num_sent     : Number of rows sent, used for the update of the statistics
    Raises:
    """
    
    global _recreate_omf_objects

    is_data_sent = False
    config_category_name = data['_CONFIG_CATEGORY_NAME']
    type_id = _config_omf_types['type-id']['value']

    # Sets globals for the OMF module
    omf._logger = _logger
    omf._log_debug_level = _log_debug_level
    omf._log_performance = _log_performance

    ocs_north = OCSNorthPlugin(data['sending_process_instance'], data, _config_omf_types, _logger)

    try:
        # Create Types
        await ocs_north._create_omf_object_types(raw_data, config_category_name, type_id)

        # Create Containers
        await ocs_north._create_omf_object_containers()

        # Create Links
        await ocs_north._create_omf_object_links()

        # Create Static
        await ocs_north._create_omf_object_static()

        # Create Data
        data_to_send, last_id = ocs_north.create_omf_data(raw_data)
        num_to_sent = len(data_to_send)

        # Send Data
        await ocs_north.send_to_pi("data", data_to_send)
        is_data_sent = True
    except Exception as ex:
        _logger.exception(plugin_common.MESSAGES_LIST["e000031"].format(ex))
        if _recreate_omf_objects:  # Forces the recreation of PIServer's objects on the first error occurred
            await ocs_north.deleted_omf_types_already_created(config_category_name, type_id)
            _recreate_omf_objects = False
            _logger.debug("{0} - Forces objects recreation ".format("plugin_send"))
        raise ex

    return is_data_sent, last_id, num_to_sent


def plugin_shutdown(data):
    pass

def plugin_reconfigure():
    pass


class OCSNorthPlugin(omf.OmfNorthPlugin):
    """ North OCS North Plugin """
    def __init__(self, sending_process_instance, config, config_omf_types,  _logger):
        super().__init__(sending_process_instance, config, config_omf_types, _logger)

    async def _create_omf_type_automatic(self, asset_info):
        type_id = self._config_omf_types["type-id"]["value"]
        sensor_id = asset_info["asset_code"].replace(" ", "")
        typename = sensor_id + _OMF_SUFFIX_TYPENAME
        static_id = type_id + "_" + typename + "_sensor"
        dynamic_id = type_id + "_" + typename + "_measurement"

        asset_data = asset_info["asset_data"]

        static_omf_type = omf.OmfType(). \
            add_id(static_id). \
            add_type("object"). \
            add_classfication('static'). \
            add_version('1.0.0.0'). \
            chain_payload()
        static_omf_type.add_property("Name", property={"type": "string", "isindex": True})
        for item in self._config['StaticData']:
            static_omf_type.add_property(item, property={"type": "string"})

        dynamic_omf_type = omf.OmfType(). \
            add_id(dynamic_id). \
            add_type("object"). \
            add_classfication('dynamic'). \
            add_version('1.0.0.0'). \
            chain_payload()
        dynamic_omf_type.add_property("Time", property={"type": "string", "format": "date-time", "isindex": True})
        for item in asset_data:
            item_type = plugin_common.evaluate_type(asset_data[item])
            if item_type == "integer":
                property = {"type": item_type, "format": self._config['formatInteger']}
            elif item_type == "number":
                property = {"type": item_type, "format": self._config['formatNumber']}
            else:
                property = {"type": item_type}
            dynamic_omf_type.add_property(item, property=property)

        omf_type = [static_omf_type.payload(), dynamic_omf_type.payload()]

        self._new_types.append({
            "sensor_id": sensor_id,
            "typename": typename,
            "static_id": static_id,
            "dynamic_id": dynamic_id,
        })

        self._new_config_types[asset_info["asset_code"]] = {
            'static': static_omf_type.payload(),
            'dynamic': dynamic_omf_type.payload()
        }
        await self.send_to_pi("type", omf_type)

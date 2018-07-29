# -*- coding: utf-8 -*-

# FOGLAMP_BEGIN
# See: http://foglamp.readthedocs.io/
# FOGLAMP_END

""" The OMF North is a plugin output formatter for the FogLAMP appliance.
    It is loaded by the send process (see The FogLAMP Sending Process) and runs in the context of the send process,
    to send the reading data to a PI Server (or Connector) using the OSIsoft OMF format.
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

__author__ = "Stefano Simonelli, Amarendra K Sinha"
__copyright__ = "Copyright (c) 2017 OSIsoft, LLC"
__license__ = "Apache 2.0"
__version__ = "${VERSION}"

_logger = None
_MODULE_NAME = "omf_north"
_log_debug_level = 0
_log_performance = False
_stream_id = None
_destination_id = None
_config_omf_types = {}
_config = {}
_recreate_omf_objects = True
_CONFIG_CATEGORY_DESCRIPTION = 'OMF North Plugin'
_CONFIG_DEFAULT_OMF = {
    'plugin': {
        'description': 'OMF North Plugin',
        'type': 'string',
        'default': 'omf'
    },
    "URL": {
        "description": "URL of PI Connector to send data to",
        "type": "string",
        "default": "https://pi-server:5460/ingress/messages"
    },
    "producerToken": {
        "description": "Producer token for this FogLAMP stream",
        "type": "string",
        "default": "omf_north_0001"
    },
    "OMFMaxRetry": {
        "description": "Max number of retries for communication with the OMF PI Connector Relay",
        "type": "integer",
        "default": "3"
    },
    "OMFRetrySleepTime": {
        "description": "Seconds between each retry for communication with the OMF PI Connector Relay. "
                       "This time is doubled at each attempt.",
        "type": "integer",
        "default": "1"
    },
    "OMFHttpTimeout": {
        "description": "Timeout in seconds for HTTP operations with the OMF PI Connector Relay",
        "type": "integer",
        "default": "10"
    },
    "StaticData": {
        "description": "Static data to include in each sensor reading sent via OMF",
        "type": "JSON",
        "default": json.dumps(
            {
                "Location": "Palo Alto",
                "Company": "Dianomic"
            }
        )
    },
    "applyFilter": {
        "description": "Should filter be applied before processing the data?",
        "type": "boolean",
        "default": "False"
    },
    "filterRule": {
        "description": "JQ formatted filter to apply (only applicable if applyFilter is True)",
        "type": "string",
        "default": ".[]"
    }
}

# Configuration related to the OMF Types
_CONFIG_CATEGORY_OMF_TYPES_NAME = 'OMF_TYPES'
_CONFIG_CATEGORY_OMF_TYPES_DESCRIPTION = 'OMF Types'
_OMF_PREFIX_MEASUREMENT = "measurement_"
_OMF_SUFFIX_TYPENAME = "_typename"
_CONFIG_DEFAULT_OMF_TYPES = {
    "type-id": {
        "description": "Identify sensor and measurement types",
        "type": "integer",
        "default": "0001"
    },
}


def plugin_info():
    return {
        'name': "OMF North",
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
    _config['sending_process_instance'] = data['sending_process_instance']

    # Fetch and validate OMF_TYPES fetched from configuration
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
    for item in _config_omf_types:  # Converts the value field from str to a dict
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

    omf_north = OmfNorthPlugin(data['sending_process_instance'], data, _config_omf_types, _logger)

    try:
        # Create Types
        await omf_north._create_omf_object_types(raw_data, config_category_name, type_id)

        # Create Containers
        await omf_north._create_omf_object_containers()

        # Create Links
        await omf_north._create_omf_object_links()

        # Create Static
        await omf_north._create_omf_object_static()

        # Create Data
        data_to_send, last_id = omf_north.create_omf_data(raw_data)
        num_to_sent = len(data_to_send)

        # Send Data
        await omf_north.send_to_pi("data", data_to_send)
        is_data_sent = True
    except Exception as ex:
        _logger.exception(plugin_common.MESSAGES_LIST["e000031"].format(ex))
        if _recreate_omf_objects:  # Forces the recreation of PIServer's objects on the first error occurred
            await omf_north.deleted_omf_types_already_created(config_category_name, type_id)
            _recreate_omf_objects = False
            _logger.debug("{0} - Forces objects recreation ".format("plugin_send"))
        raise ex

    return is_data_sent, last_id, num_to_sent


def plugin_shutdown(data):
    pass


def plugin_reconfigure():
    pass


class OmfType:
    type_payload = None

    def __init__(self):
        self.type_payload = dict()
        self.type_payload['properties'] = dict()

    def check_property(self, property):
        if not isinstance(property, dict):
            return False
        is_valid = True
        for i, v in property.items():
            if i not in ['type', 'format', 'isindex', 'isname', 'name', 'description', 'uom']:
                is_valid = False
                break
            if i == 'type' and v not in ['array', 'object', 'boolean', 'integer', 'string', 'number',
                                         'additionalProperties']:
                is_valid = False
                break
            if i == 'type' and v == 'array':
                if 'items' not in v:
                    is_valid = False
                    break
                if not isinstance(v['items'], dict):
                    is_valid = False
                    break
                is_valid = self.check_property(property['items'])
            if i == 'type' and v == 'object':
                if 'properties' not in v and 'additionalProperties' not in v:
                    is_valid = False
                    break
                if 'properties' in v and not isinstance(v['properties'], dict):
                    is_valid = False
                    break
                if 'additionalProperties' in v and not isinstance(v['additionalProperties'], dict):
                    is_valid = False
                    break
                is_valid = self.check_property(property['properties'])

        return is_valid

    def add_id(self, id):
        self.type_payload['id'] = id
        return self

    def add_version(self, version=None):
        if version is None:
            version = '1.0.0.0'
        self.type_payload['version'] = version
        return self

    def add_type(self, item_type):
        self.type_payload['type'] = 'object'
        return self

    def add_classfication(self, classification):
        if classification not in ['static', 'dynamic']:
            classification = 'static'
        self.type_payload['classification'] = classification
        return self

    def add_property(self, name, property):
        if self.check_property(property) is True:
            self.type_payload['properties'][name] = property
        return self

    def chain_payload(self):
        return self

    def payload(self):
        return self.type_payload


class OmfContainer:
    container_payload = None

    def __init__(self):
        self.container_payload = dict()

    def add_id(self, id):
        self.container_payload['id'] = id
        return self

    def add_typeid(self, type_id):
        self.container_payload['typeid'] = type_id
        return self

    def add_typeversion(self, type_version):
        self.container_payload['typeversion'] = type_version
        return self

    def add_name(self, name):
        self.container_payload['name'] = name
        return self

    def add_description(self, description):
        self.container_payload['description'] = description
        return self

    def add_tags(self, tags):
        if not isinstance(tags, list):
            tags = list(tags)
        self.container_payload['tags'] = tags
        return self

    def add_metadata(self, metadata):
        if isinstance(metadata, dict):
            self.container_payload['metadata'] = metadata
        return self

    def add_indexes(self, indexes):
        if not isinstance(indexes, list):
            indexes = list(indexes)
        self.container_payload['indexes'] = indexes
        return self

    def chain_payload(self):
        return self

    def payload(self):
        return self.container_payload


class OmfData:
    data_payload = None

    def __init__(self):
        self.data_payload = dict()
        self.data_payload['values'] = list()

    def add_containerid(self, container_id):
        self.data_payload['containerid'] = container_id
        return self

    def add_typeid(self, type_id):
        self.data_payload['typeid'] = type_id
        return self

    def add_typeversion(self, type_version):
        self.data_payload['typeversion'] = type_version
        return self

    def add_values(self, value):
        self.data_payload['values'].append(value)
        return self

    def chain_payload(self):
        return self

    def payload(self):
        return self.data_payload


class OmfNorthPlugin(object):
    """ North OMF North Plugin """

    def __init__(self, sending_process_instance, config, config_omf_types, _logger):
        self._sending_process_instance = sending_process_instance
        self._config = config
        self._config_omf_types = config_omf_types
        self._logger = _logger
        self._new_types = list()
        self._new_config_types = dict()

    async def deleted_omf_types_already_created(self, config_category_name, type_id):
        """ Deletes OMF types/objects tracked as already created, it is used to force the recreation of the types"""
        try:
            payload = payload_builder.PayloadBuilder() \
                .WHERE(['configuration_key', '=', config_category_name]) \
                .AND_WHERE(['type_id', '=', type_id]) \
                .payload()
            await self._sending_process_instance._storage_async.delete_from_tbl("omf_created_objects", payload)
        except StorageServerError as ex:
            err_response = ex.error
            _logger.error("%s, %s", err_response["source"], err_response["message"])

    async def _retrieve_omf_types_already_created(self, configuration_key, type_id):
        """ Retrieves the list of OMF types already defined/sent to the PICROMF"""
        try:
            payload = payload_builder.PayloadBuilder() \
                .SELECT('asset_code') \
                .WHERE(['configuration_key', '=', configuration_key]) \
                .AND_WHERE(['type_id', '=', type_id]) \
                .payload()
            omf_created_objects = await self._sending_process_instance._storage_async.query_tbl_with_payload(
                'omf_created_objects', payload)
        except StorageServerError as ex:
            err_response = ex.error
            _logger.error("%s, %s", err_response["source"], err_response["message"])

        # Extracts only the asset_code column
        rows = []
        for row in omf_created_objects['rows']:
            rows.append(row['asset_code'])
        return rows

    async def _flag_created_omf_type(self, configuration_key, type_id, asset_code):
        """ Stores into the Storage layer the successfully creation of the type into PICROMF."""
        try:
            payload = payload_builder.PayloadBuilder() \
                .INSERT(configuration_key=configuration_key,
                        asset_code=asset_code,
                        type_id=type_id) \
                .payload()
            await self._sending_process_instance._storage_async.insert_into_tbl("omf_created_objects", payload)
        except StorageServerError as ex:
            err_response = ex.error
            _logger.error("%s, %s", err_response["source"], err_response["message"])

    def _generate_omf_container_id(self, asset_code):
        """ Generates the measurement id associated to an asset code"""
        asset_id = asset_code.replace(" ", "")
        type_id = self._config_omf_types['type-id']['value']
        return type_id + "_" + _OMF_PREFIX_MEASUREMENT + asset_id

    async def _create_omf_types_automatic(self, asset_info):
        type_id = self._config_omf_types["type-id"]["value"]
        sensor_id = asset_info["asset_code"].replace(" ", "")
        typename = sensor_id + _OMF_SUFFIX_TYPENAME
        static_id = type_id + "_" + typename + "_sensor"
        dynamic_id = type_id + "_" + typename + "_measurement"

        asset_data = asset_info["asset_data"]

        static_omf_type = OmfType(). \
            add_id(static_id). \
            add_type("object"). \
            add_classfication('static'). \
            add_version('1.0.0.0'). \
            chain_payload()
        static_omf_type.add_property("Name", property={"type": "string", "isindex": True})
        for item in self._config['StaticData']:
            static_omf_type.add_property(item, property={"type": "string"})

        dynamic_omf_type = OmfType(). \
            add_id(dynamic_id). \
            add_type("object"). \
            add_classfication('dynamic'). \
            add_version('1.0.0.0'). \
            chain_payload()
        dynamic_omf_type.add_property("Time", property={"type": "string", "format": "date-time", "isindex": True})
        for item in asset_data:
            item_type = plugin_common.evaluate_type(asset_data[item])
            dynamic_omf_type.add_property(item, property={"type": item_type})

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

    async def _create_omf_types_configuration_based(self, asset_code):
        asset_code_omf_type = copy.deepcopy(self._config_omf_types[asset_code]["value"])

        type_id = self._config_omf_types["type-id"]["value"]
        sensor_id = asset_code.replace(" ", "")
        typename = sensor_id + _OMF_SUFFIX_TYPENAME

        for item in self._config_omf_types[asset_code]["value"]:
            self._new_types.append({
                "sensor_id": sensor_id,
                "typename": typename,
                "static_id": item['static']['id'],
                "dynamic_id": item['dynamic']['id'],
            })
        await self.send_to_pi("type", asset_code_omf_type)

    async def _create_omf_object_types(self, raw_data, config_category_name, type_id):
        """ Handles the creation of the OMF types related to the asset codes using one of the 2 possible ways :
                Automatic OMF Type Mapping
                Configuration Based OMF Type Mapping
        """
        if len(raw_data) == 0:
            return

        asset_codes_to_evaluate = plugin_common.identify_unique_asset_codes(raw_data)
        asset_codes_already_created = await self._retrieve_omf_types_already_created(config_category_name, type_id)

        for item in asset_codes_to_evaluate:
            asset_code = item["asset_code"]
            if not any(tmp_item == asset_code for tmp_item in asset_codes_already_created):
                try:
                    assert asset_code in self._config_omf_types
                except (KeyError, AssertionError):
                    await self._create_omf_types_automatic(item)  # configuration_based = False
                else:
                    await self._create_omf_types_configuration_based(asset_code)  # configuration_based = True
                await self._flag_created_omf_type(config_category_name, type_id, asset_code)

    async def _create_omf_object_containers(self):
        containers = list()
        for item in self._new_types:
            sensor_id = item['sensor_id']
            container_id = self._generate_omf_container_id(sensor_id)
            container = OmfContainer()
            container.add_id(container_id).add_typeid(item['dynamic_id']).add_typeversion('1.0.0.0')
            containers.append(container.payload())
        if len(containers) > 0:
            await self.send_to_pi("container", containers)

    async def _create_omf_object_static(self):
        static_data = list()
        for item in self._new_types:
            data = OmfData()
            values = {"Name": item['sensor_id']}
            values.update(copy.deepcopy(self._config['StaticData']))
            data.add_typeid(item['static_id']).add_values(values)
            static_data.append(data.payload())
        if len(static_data) > 0:
            await self.send_to_pi("data", static_data)

    async def _create_omf_object_links(self):
        link_data = list()
        data = OmfData()
        data.add_typeid('__Link')
        for item in self._new_types:
            sensor_id = item['sensor_id']
            link_1 = {
                "source": {
                    "typeid": item["static_id"]
                },
                "target": {
                    "typeid": item["static_id"],
                    "index": sensor_id
                }
            }
            link_2 = {
                "source": {
                    "typeid": item["static_id"],
                    "index": sensor_id
                },
                "target": {
                    "containerid": item["dynamic_id"],
                }
            }
            data.add_values(link_1).add_values(link_2)
        link_data.append(data.payload())
        if len(link_data[0]['values']) > 0:
            await self.send_to_pi("data", link_data)

    async def send_to_pi(self, message_type, omf_data):
        """ Sends data to PICROMF - it retries the operation using a sleep time increased *2 for every retry"""
        sleep_time = self._config['OMFRetrySleepTime']
        _message = None
        _error = None
        _is_error = False
        num_retry = 1

        msg_header = {'producertoken': self._config['producerToken'],
                      'messagetype': message_type,
                      'action': 'create',
                      'messageformat': 'JSON',
                      'omfversion': '1.0'}
        omf_data_json = json.dumps(omf_data)

        while num_retry <= self._config['OMFMaxRetry']:
            _is_error = False
            try:
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as session:
                    async with session.post(url=self._config['URL'],
                                            headers=msg_header,
                                            data=omf_data_json,
                                            timeout=self._config['OMFHttpTimeout']
                                            ) as resp:
                        status_code = resp.status
                        text = await resp.text()
                        if not str(status_code).startswith('2'):  # Evaluate the HTTP status codes
                            raise RuntimeError(str(status_code) + " " + text)
            except RuntimeError as e:
                _message = "an error occurred during the request to the destination - error details |{0}|".format(e)
                _error = plugin_exceptions.URLFetchError(_message)
                _is_error = True
            except Exception as e:
                _message = "an error occurred during the request to the destination - error details |{0}|".format(e)
                __error = Exception(_message)
                _is_error = True

            if _is_error is True:
                time.sleep(sleep_time)
                num_retry += 1
                sleep_time *= 2
            else:
                break

        if _is_error is True:
            self._logger.warning(_message)
            raise _error

    def create_omf_data(self, raw_data):
        """ Transforms the in memory data into a new structure that could be converted into JSON for the PICROMF"""
        _last_id = 0
        data_to_send = list()

        for row in raw_data:
            container_id = self._generate_omf_container_id(row['asset_code'])
            try:
                # The expression **row['reading'] - joins the 2 dictionaries
                #
                # The code formats the date to the format OMF/the PI Server expects directly
                # without using python date library for performance reason and
                # because it is expected to receive the date in a precise/fixed format :
                #   2018-05-28 16:56:55.000000+00
                value = {
                    "Time": row['user_ts'][0:10] + "T" + row['user_ts'][11:23] + "Z",
                    **row['reading']
                }
                data = OmfData()
                data.add_containerid(container_id).add_values(value)
                data_to_send.append(data.payload())
                _last_id = row['id']  # Latest position reached
            except Exception as e:
                self._logger.warning(
                    "cannot prepare sensor information for the destination - error details |{0}|".format(e))
        return data_to_send, _last_id

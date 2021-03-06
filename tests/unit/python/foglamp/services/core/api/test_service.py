# -*- coding: utf-8 -*-

# FOGLAMP_BEGIN
# See: http://foglamp.readthedocs.io/
# FOGLAMP_END


import asyncio
import json
from aiohttp import web
import pytest
from unittest.mock import MagicMock, patch, call
from foglamp.services.core import routes
from foglamp.services.core import connect
from foglamp.common.storage_client.storage_client import StorageClientAsync
from foglamp.services.core.service_registry.service_registry import ServiceRegistry
from foglamp.services.core.interest_registry.interest_registry import InterestRegistry
from foglamp.services.core import server
from foglamp.services.core.scheduler.scheduler import Scheduler
from foglamp.services.core.scheduler.entities import StartUpSchedule
from foglamp.common.configuration_manager import ConfigurationManager

__author__ = "Ashwin Gopalakrishnan, Ashish Jabble"
__copyright__ = "Copyright (c) 2017 OSIsoft, LLC"
__license__ = "Apache 2.0"
__version__ = "${VERSION}"


@pytest.allure.feature("unit")
@pytest.allure.story("api", "service")
class TestService:
    def setup_method(self):
        ServiceRegistry._registry = list()

    def teardown_method(self):
        ServiceRegistry._registry = list()

    @pytest.fixture
    def client(self, loop, test_client):
        app = web.Application(loop=loop)
        # fill the routes table
        routes.setup(app)
        return loop.run_until_complete(test_client(app))

    async def test_get_health(self, mocker, client):
        # empty service registry
        resp = await client.get('/foglamp/service')
        assert 200 == resp.status
        result = await resp.text()
        json_response = json.loads(result)
        assert {'services': []} == json_response

        mocker.patch.object(InterestRegistry, "__init__", return_value=None)
        mocker.patch.object(InterestRegistry, "get", return_value=list())

        with patch.object(ServiceRegistry._logger, 'info') as log_patch_info:
            # populated service registry
            s_id_1 = ServiceRegistry.register(
                'name1', 'Storage', 'address1', 1, 1, 'protocol1')
            s_id_2 = ServiceRegistry.register(
                'name2', 'Southbound', 'address2', 2, 2, 'protocol2')
            s_id_3 = ServiceRegistry.register(
                'name3', 'Southbound', 'address3', 3, 3, 'protocol3')
            s_id_4 = ServiceRegistry.register(
                'name4', 'Southbound', 'address4', 4, 4, 'protocol4')

            ServiceRegistry.unregister(s_id_3)
            ServiceRegistry.mark_as_failed(s_id_4)

            resp = await client.get('/foglamp/service')
            assert 200 == resp.status
            result = await resp.text()
            json_response = json.loads(result)
            assert json_response == {
                        'services': [
                            {
                                'type': 'Storage',
                                'service_port': 1,
                                'address': 'address1',
                                'protocol': 'protocol1',
                                'status': 'running',
                                'name': 'name1',
                                'management_port': 1
                            },
                            {
                                'type': 'Southbound',
                                'service_port': 2,
                                'address': 'address2',
                                'protocol': 'protocol2',
                                'status': 'running',
                                'name': 'name2',
                                'management_port': 2
                            },
                            {
                                'type': 'Southbound',
                                'service_port': 3,
                                'address': 'address3',
                                'protocol': 'protocol3',
                                'status': 'down',
                                'name': 'name3',
                                'management_port': 3
                            },
                            {
                                'type': 'Southbound',
                                'service_port': 4,
                                'address': 'address4',
                                'protocol': 'protocol4',
                                'status': 'failed',
                                'name': 'name4',
                                'management_port': 4
                            }
                        ]
            }
        assert 6 == log_patch_info.call_count

    @pytest.mark.parametrize("payload, code, message", [
        ('"blah"', 404, "Data payload must be a dictionary"''),
        ('{}', 400, "Missing name property in payload."),
        ('{"name": "test"}', 400, "Missing plugin property in payload."),
        ('{"name": "a;b", "plugin": "dht11", "type": "south"}', 400, "Invalid name property in payload."),
        ('{"name": "test", "plugin": "dht@11", "type": "south"}', 400, "Invalid plugin property in payload."),
        ('{"name": "test", "plugin": "dht11", "type": "south", "enabled": "blah"}', 400,
         'Only "true", "false", true, false are allowed for value of enabled.'),
        ('{"name": "test", "plugin": "dht11", "type": "south", "enabled": "t"}', 400,
         'Only "true", "false", true, false are allowed for value of enabled.'),
        ('{"name": "test", "plugin": "dht11", "type": "south", "enabled": "True"}', 400,
         'Only "true", "false", true, false are allowed for value of enabled.'),
        ('{"name": "test", "plugin": "dht11", "type": "south", "enabled": "False"}', 400,
         'Only "true", "false", true, false are allowed for value of enabled.'),
        ('{"name": "test", "plugin": "dht11", "type": "south", "enabled": "1"}', 400,
         'Only "true", "false", true, false are allowed for value of enabled.'),
        ('{"name": "test", "plugin": "dht11", "type": "south", "enabled": "0"}', 400,
         'Only "true", "false", true, false are allowed for value of enabled.'),
        ('{"name": "test", "plugin": "dht11"}', 400, "Missing type property in payload."),
        ('{"name": "test", "plugin": "dht11", "type": "blah"}', 400, "Only south type is supported."),
        ('{"name": "test", "plugin": "dht11", "type": "North"}', 406, "north type is not supported for the time being.")
    ])
    async def test_add_service_with_bad_params(self, client, code, payload, message):
        resp = await client.post('/foglamp/service', data=payload)
        assert code == resp.status
        assert message == resp.reason

    async def test_insert_scheduled_process_exception_add_service(self, client):
        data = {"name": "furnace4", "type": "south", "plugin": "dht11"}

        @asyncio.coroutine
        def async_mock():
            expected = {'count': 0, 'rows': []}
            return expected

        storage_client_mock = MagicMock(StorageClientAsync)
        with patch('builtins.__import__', side_effect=MagicMock()):
            with patch.object(connect, 'get_storage_async', return_value=storage_client_mock):
                with patch.object(storage_client_mock, 'query_tbl_with_payload', return_value=async_mock()) as query_table_patch:
                    with patch.object(storage_client_mock, 'insert_into_tbl', side_effect=Exception()) as insert_table_patch:
                        resp = await client.post('/foglamp/service', data=json.dumps(data))
                        assert 500 == resp.status
                        assert 'Failed to created scheduled process. ' == resp.reason
                args1, kwargs1 = query_table_patch.call_args
                assert 'scheduled_processes' == args1[0]
                p2 = json.loads(args1[1])
                assert {'return': ['name'], 'where': {'column': 'name', 'condition': '=', 'value': 'south'}} == p2

    async def test_dupe_schedule_name_add_service(self, client):
        def q_result(*arg):
            table = arg[0]
            payload = arg[1]

            if table == 'scheduled_processes':
                assert {'return': ['name'], 'where': {'column': 'name', 'condition': '=', 'value': 'south'}} == json.loads(payload)
                return {'count': 0, 'rows': []}
            if table == 'schedules':
                assert {'return': ['schedule_name'], 'where': {'column': 'schedule_name', 'condition': '=', 'value': 'furnace4'}} == json.loads(payload)
                return {'count': 1, 'rows': [{'schedule_name': 'schedule_name'}]}

        @asyncio.coroutine
        def async_mock():
            expected = {'rows_affected': 1, "response": "inserted"}
            return expected

        data = {"name": "furnace4", "type": "south", "plugin": "dht11"}
        description = '{} service configuration'.format(data['name'])
        storage_client_mock = MagicMock(StorageClientAsync)
        c_mgr = ConfigurationManager(storage_client_mock)
        val = {'plugin': {'default': data['plugin'], 'description': 'Python module name of the plugin to load', 'type': 'string'}}
        with patch('builtins.__import__', side_effect=MagicMock()):
            with patch.object(connect, 'get_storage_async', return_value=storage_client_mock):
                with patch.object(storage_client_mock, 'query_tbl_with_payload', side_effect=q_result):
                    with patch.object(storage_client_mock, 'insert_into_tbl', return_value=async_mock()) as insert_table_patch:
                        with patch.object(c_mgr, 'create_category', return_value=None) as patch_create_cat:
                            with patch.object(c_mgr, 'create_child_category', return_value=async_mock(None)) as patch_create_child_cat:
                                resp = await client.post('/foglamp/service', data=json.dumps(data))
                                assert 500 == resp.status
                                assert 'Internal Server Error' == resp.reason
                            assert 0 == patch_create_cat.call_count

    p1 = '{"name": "furnace4", "type": "south", "plugin": "dht11"}'
    p2 = '{"name": "furnace4", "type": "south", "plugin": "dht11", "enabled": false}'
    p3 = '{"name": "furnace4", "type": "south", "plugin": "dht11", "enabled": true}'
    p4 = '{"name": "furnace4", "type": "south", "plugin": "dht11", "enabled": "true"}'
    p5 = '{"name": "furnace4", "type": "south", "plugin": "dht11", "enabled": "false"}'

    @pytest.mark.parametrize("payload", [p1, p2, p3, p4, p5])
    async def test_add_service(self, client, payload):

        data = json.loads(payload)

        @asyncio.coroutine
        def async_mock(return_value):
            return return_value

        async def async_mock_get_schedule():
            schedule = StartUpSchedule()
            schedule.schedule_id = '2129cc95-c841-441a-ad39-6469a87dbc8b'
            return schedule

        @asyncio.coroutine
        def q_result(*arg):
            table = arg[0]
            payload = arg[1]

            if table == 'scheduled_processes':
                assert {'return': ['name'], 'where': {'column': 'name', 'condition': '=', 'value': 'south'}} == json.loads(payload)
                return {'count': 0, 'rows': []}
            if table == 'schedules':
                assert {'return': ['schedule_name'], 'where': {'column': 'schedule_name', 'condition': '=', 'value': 'furnace4'}} == json.loads(payload)
                return {'count': 0, 'rows': []}

        async def async_mock_insert():
            expected = {'rows_affected': 1, "response": "inserted"}
            return expected

        mock_plugin_info = {
                'name': "furnace4",
                'version': "1.1",
                'type': "south",
                'interface': "1.0",
                'config': {
                            'plugin': {
                                'description': "Modbus RTU plugin",
                                'type': 'string',
                                'default': 'dht11'
                            }
            }
        }

        mock = MagicMock()
        attrs = {"plugin_info.side_effect": [mock_plugin_info]}
        mock.configure_mock(**attrs)

        server.Server.scheduler = Scheduler(None, None)

        description = "Modbus RTU plugin"

        storage_client_mock = MagicMock(StorageClientAsync)
        c_mgr = ConfigurationManager(storage_client_mock)
        val = {'plugin': {'default': data['plugin'], 'description': 'Modbus RTU plugin', 'type': 'string'}}

        with patch('builtins.__import__', return_value=mock):
            with patch.object(connect, 'get_storage_async', return_value=storage_client_mock):
                with patch.object(storage_client_mock, 'query_tbl_with_payload', side_effect=q_result):
                    with patch.object(storage_client_mock, 'insert_into_tbl', return_value=async_mock_insert()) as insert_table_patch:
                        with patch.object(c_mgr, 'create_category', return_value=async_mock(None)) as patch_create_cat:
                            with patch.object(c_mgr, 'create_child_category', return_value=async_mock(None)) as patch_create_child_cat:
                                with patch.object(server.Server.scheduler, 'save_schedule', return_value=async_mock("")) as patch_save_schedule:
                                    with patch.object(server.Server.scheduler, 'get_schedule_by_name', return_value=async_mock_get_schedule()) as patch_get_schedule:
                                        resp = await client.post('/foglamp/service', data=payload)
                                        server.Server.scheduler = None
                                        assert 200 == resp.status
                                        result = await resp.text()
                                        json_response = json.loads(result)
                                        assert {'id': '2129cc95-c841-441a-ad39-6469a87dbc8b', 'name': 'furnace4'} == json_response
                                    patch_get_schedule.assert_called_once_with(data['name'])
                                patch_save_schedule.called_once_with()
                                calls = [call(category_description='Modbus RTU plugin', category_name='furnace4', category_value={'plugin': {'description': 'Modbus RTU plugin', 'type': 'string', 'default': 'dht11'}}, keep_original_items=True),
                                         call('South', {}, 'South microservices', True)]
                            patch_create_cat.assert_has_calls(calls)

                        args, kwargs = insert_table_patch.call_args
                        assert 'scheduled_processes' == args[0]
                        p = json.loads(args[1])
                        assert {'name': 'south', 'script': '["services/south"]'} == p

# TODO add negative tests and C type plugin add service tests
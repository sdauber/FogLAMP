-- North_Readings_to_PI - OMF Translator for readings
INSERT INTO foglamp.configuration ( key, description, value )
     SELECT 'North_Readings_to_PI',
              'OMF North Plugin - C Code',
              ' { "plugin" : { "type" : "string", "value" : "omf", "default" : "omf", "description" : "Module that OMF North Plugin will load" } } '
            WHERE NOT EXISTS (SELECT 1 FROM foglamp.configuration WHERE key = 'North_Readings_to_PI');

-- North_Readings_to_HTTP - for readings
INSERT INTO foglamp.configuration ( key, description, value )
     SELECT 'North_Readings_to_HTTP',
              'HTTP North Plugin - C Code',
              ' { "plugin" : { "type" : "string", "value" : "http-north", "default" : "http-north", "description" : "Module that HTTP North Plugin will load" } } '
            WHERE NOT EXISTS (SELECT 1 FROM foglamp.configuration WHERE key = 'North_Readings_to_HTTP');

-- dht11 - South plugin for DHT11 - C
INSERT INTO foglamp.configuration ( key, description, value )
     SELECT 'dht11',
              'DHT11 South C Plugin',
              ' { "plugin" : { "type" : "string", "value" : "dht11", "default" : "dht11", "description" : "Module that DHT11 South Plugin will load" } } '
            WHERE NOT EXISTS (SELECT 1 FROM foglamp.configuration WHERE key = 'dht11');

-- North_Statistics_to_PI - OMF Translator for statistics
INSERT INTO foglamp.configuration ( key, description, value )
     SELECT 'North_Statistics_to_PI',
              'OMF North Plugin - C Code',
              ' { "plugin" : { "type" : "string", "value" : "omf", "default" : "omf", "description" : "Module that OMF North Plugin will load" } } '
            WHERE NOT EXISTS (SELECT 1 FROM foglamp.configuration WHERE key = 'North_Statistics_to_PI');

-- North Readings to PI - OMF Translator for readings
INSERT INTO foglamp.configuration ( key, description, value )
     SELECT 'North Readings to PI',
              'OMF North Plugin',
              '{"plugin": {"description": "OMF North Plugin", "type": "string", "default": "omf", "value": "omf"}, "source": {"description": "Source of data to be sent on the stream. May be either readings, statistics or audit.", "type": "string", "default": "readings", "value": "readings"}}'
            WHERE NOT EXISTS (SELECT 1 FROM foglamp.configuration WHERE key = 'North Readings to PI');

-- North Statistics to PI - OMF Translator for statistics
INSERT INTO foglamp.configuration ( key, description, value )
     SELECT 'North Statistics to PI',
              'OMF North Statistics Plugin',
              '{"plugin": {"description": "OMF North Plugin", "type": "string", "default": "omf", "value": "omf"}, "source": {"description": "Source of data to be sent on the stream. May be either readings, statistics or audit.", "type": "string", "default": "statistics", "value": "statistics"}}'
            WHERE NOT EXISTS (SELECT 1 FROM foglamp.configuration WHERE key = 'North Statistics to PI');

-- North Readings to OCS - OSIsoft Cloud Services plugin for readings
INSERT INTO foglamp.configuration ( key, description, value )
     SELECT 'North Readings to OCS',
              'OCS North Plugin',
              '{"plugin": {"description": "OCS North Plugin", "type": "string", "default": "ocs", "value": "ocs"}, "source": {"description": "Source of data to be sent on the stream. May be either readings, statistics or audit.", "type": "string", "default": "readings", "value": "readings"}}'
            WHERE NOT EXISTS (SELECT 1 FROM foglamp.configuration WHERE key = 'North Readings to OCS');

-- Readings OMF to PI - C Code
INSERT INTO foglamp.schedules ( id, schedule_name, process_name, schedule_type,
                                schedule_time, schedule_interval, exclusive, enabled )
       SELECT '1cdf1ef8-7e02-11e8-adc0-fa7ae01bbebc', -- id
                'OMF_to_PI_north_C',                    -- schedule_name
                'North_Readings_to_PI',                 -- process_name
                3,                                      -- schedule_type (interval)
                NULL,                                   -- schedule_time
                '00:00:30',                             -- schedule_interval
                't',                                    -- exclusive
                'f'                                     -- disabled
       WHERE NOT EXISTS (SELECT 1 FROM foglamp.schedules WHERE id = '1cdf1ef8-7e02-11e8-adc0-fa7ae01bbebc');

-- Statistics OMF to PI - C Code
INSERT INTO foglamp.schedules ( id, schedule_name, process_name, schedule_type,
                                schedule_time, schedule_interval, exclusive, enabled )
       SELECT 'f1e3b377-5acb-4bde-93d5-b6a792f76e07', -- id
                'Stats_OMF_to_PI_north_C',              -- schedule_name
                'North_Statistics_to_PI',               -- process_name
                3,                                      -- schedule_type (interval)
                NULL,                                   -- schedule_time
                '00:00:30',                             -- schedule_interval
                't',                                    -- exclusive
                'f'                                     -- disabled
       WHERE NOT EXISTS (SELECT 1 FROM foglamp.schedules WHERE id = 'f1e3b377-5acb-4bde-93d5-b6a792f76e07');

-- Readings to HTTP - C Code
INSERT INTO foglamp.schedules ( id, schedule_name, process_name, schedule_type,
                                schedule_time, schedule_interval, exclusive, enabled )
       SELECT 'ccdf1ef8-7e02-11e8-adc0-fa7ae01bb3bc', -- id
                'HTTP_North_C',                         -- schedule_name
                'North_Readings_to_HTTP',               -- process_name
                3,                                      -- schedule_type (interval)
                NULL,                                   -- schedule_time
                '00:00:30',                             -- schedule_interval
                't',                                    -- exclusive
                'f'                                     -- disabled
       WHERE NOT EXISTS (SELECT 1 FROM foglamp.schedules WHERE id = 'ccdf1ef8-7e02-11e8-adc0-fa7ae01bb3bc');


-- DHT11 sensor south plugin - C Code
INSERT INTO foglamp.schedules ( id, schedule_name, process_name, schedule_type,
                                schedule_time, schedule_interval, exclusive, enabled )
       SELECT '6b25f4d9-c7f3-4fc8-bd4a-4cf79f7055ca', -- id
                'dht11',                                -- schedule_name
                'dht11',                                -- process_name
                1,                                      -- schedule_type (interval)
                NULL,                                   -- schedule_time
                '01:00:00',                             -- schedule_interval (evey hour)
                't',                                    -- exclusive
                'fE NOT EXISTS (SELECT 1 FROM foglamp.schedules WHERE id = '
       WHERE NOT EXISTS (SELECT 1 FROM foglamp.schedules WHERE id = '6b25f4d9-c7f3-4fc8-bd4a-4cf79f7055ca');

-- Readings OMF to PI
INSERT INTO foglamp.schedules ( id, schedule_name, process_name, schedule_type,
                                schedule_time, schedule_interval, exclusive, enabled )
       SELECT '2b614d26-760f-11e7-b5a5-be2e44b06b34', -- id
                'OMF to PI north',                      -- schedule_name
                'North Readings to PI',                 -- process_name
                3,                                      -- schedule_type (interval)
                NULL,                                   -- schedule_time
                '00:00:30',                             -- schedule_interval
                't',                                   -- exclusive
                'f'                                   -- disabled
       WHERE NOT EXISTS (SELECT 1 FROM foglamp.schedules WHERE id = '2b614d26-760f-11e7-b5a5-be2e44b06b34');

-- Statistics OMF to PI
INSERT INTO foglamp.schedules ( id, schedule_name, process_name, schedule_type,
                                schedule_time, schedule_interval, exclusive, enabled )
       SELECT '1d7c327e-7dae-11e7-bb31-be2e44b06b34', -- id
                'Stats OMF to PI north',                -- schedule_name
                'North Statistics to PI',               -- process_name
                3,                                      -- schedule_type (interval)
                NULL,                                   -- schedule_time
                '00:00:30',                             -- schedule_interval
                't',                                   -- exclusive
                'f'                                   -- disabled
       WHERE NOT EXISTS (SELECT 1 FROM foglamp.schedules WHERE id = '1d7c327e-7dae-11e7-bb31-be2e44b06b34');

-- Readings OMF to OCS
INSERT INTO foglamp.schedules ( id, schedule_name, process_name, schedule_type,
                                schedule_time, schedule_interval, exclusive, enabled )
       SELECT '5d7fed92-fb9a-11e7-8c3f-9a214cf093ae', -- id
                'OMF to OCS north',                     -- schedule_name
                'North Readings to OCS',                -- process_name
                3,                                      -- schedule_type (interval)
                NULL,                                   -- schedule_time
                '00:00:30',                             -- schedule_interval
                't',                                   -- exclusive
                'f'                                   -- disabled
      WHERE NOT EXISTS (SELECT 1 FROM foglamp.schedules WHERE id = '5d7fed92-fb9a-11e7-8c3f-9a214cf093ae');


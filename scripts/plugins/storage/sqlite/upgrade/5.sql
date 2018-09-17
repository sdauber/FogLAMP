UPDATE foglamp.configuration SET value = json_set(value, '$.stream_id', json('{"type":"integer","description":"Stream ID","default":"1","value":"1"}'))
       WHERE key = 'North Readings to PI';

UPDATE foglamp.configuration SET value = json_set(value, '$.source', json('{"description": "Source of data to be sent on the stream. May be either readings, statistics or audit.", "type": "string", "default": "audit", "value": "readings"}'))
        WHERE key = 'North Readings to PI';

UPDATE foglamp.configuration SET value = json_set(value, '$.stream_id', json('{"type":"integer","description":"Stream ID","default":"2","value":"2"}'))
        WHERE key = 'North Statistics to PI';
UPDATE foglamp.configuration SET value = json_set(value, '$.source', json('{"description": "Source of data to be sent on the stream. May be either readings, statistics or audit.", "type": "string", "default": "audit", "value": "statistics"}'))
        WHERE key = 'North Statistics to PI';

UPDATE foglamp.configuration SET value = json_set(value, '$.stream_id', json('{"type":"integer","description":"Stream ID","default":"4","value":"4"}'))
        WHERE key = 'North Readings to OCS';
UPDATE foglamp.configuration SET value = json_set(value, '$.source', json('{"description": "Source of data to be sent on the stream. May be either readings, statistics or audit.", "type": "string", "default": "audit", "value": "readings"}'))
        WHERE key = 'North Readings to OCS';

UPDATE statistics SET key = 'North Readings to PI' WHERE key = 'SENT_1';
UPDATE statistics SET key = 'North Statistics to PI' WHERE key = 'SENT_2';
UPDATE statistics SET key = 'North Readings to OCS' WHERE key = 'SENT_4';

---
UPDATE foglamp.schedules SET schedule_name=process_name WHERE process_name in (select key from foglamp.configuration where json_extract(value, '$.plugin.value') = 'omf');

INSERT INTO foglamp.scheduled_processes ( name, script ) VALUES ( 'north',   '["tasks/north"]' );

UPDATE foglamp.schedules SET process_name='north' WHERE schedule_name = 'North Readings to PI' ;
UPDATE foglamp.schedules SET process_name='north' WHERE schedule_name = 'North Statistics to PI';
UPDATE foglamp.schedules SET process_name='north' WHERE schedule_name =  'North Readings to OCS';

DELETE FROM foglamp.scheduled_processes WHERE name = 'North Readings to PI' ;
DELETE FROM foglamp.scheduled_processes WHERE name = 'North Statistics to PI' ;
DELETE FROM foglamp.scheduled_processes WHERE name = 'North Readings to OCS';

INSERT INTO foglamp.configuration (key, description, value) VALUES ( 'North',   'North tasks' , '{}' );

INSERT INTO foglamp.category_children (parent, child) VALUES ( 'North',   'North Readings to PI' );
INSERT INTO foglamp.category_children (parent, child) VALUES ( 'North',   'OMF_TYPES' );

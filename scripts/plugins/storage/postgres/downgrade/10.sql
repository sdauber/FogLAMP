-- Statistics
INSERT INTO foglamp.statistics ( key, description, value, previous_value )
     SELECT 'NORTH_READINGS_TO_PI', 'Readings sent to historian', 0, 0
     WHERE NOT EXISTS (SELECT 1 FROM foglamp.statistics WHERE key = 'NORTH_READINGS_TO_PI');
INSERT INTO foglamp.statistics ( key, description, value, previous_value )
     SELECT 'NORTH_STATISTICS_TO_PI', 'Statistics sent to historian', 0, 0
     WHERE NOT EXISTS (SELECT 1 FROM foglamp.statistics WHERE key = 'NORTH_STATISTICS_TO_PI');
INSERT INTO foglamp.statistics ( key, description, value, previous_value )
     SELECT 'NORTH_READINGS_TO_HTTP', 'Readings sent to HTTP', 0, 0
     WHERE NOT EXISTS (SELECT 1 FROM foglamp.statistics WHERE key = 'NORTH_READINGS_TO_HTTP');
INSERT INTO foglamp.statistics ( key, description, value, previous_value )
     SELECT 'North Readings to PI', 'Readings sent to the historian', 0, 0
     WHERE NOT EXISTS (SELECT 1 FROM foglamp.statistics WHERE key = 'North Readings to PI');
INSERT INTO foglamp.statistics ( key, description, value, previous_value )
     SELECT 'North Statistics to PI','Statistics data sent to the historian', 0, 0
     WHERE NOT EXISTS (SELECT 1 FROM foglamp.statistics WHERE key = 'North Statistics to PI');
INSERT INTO foglamp.statistics ( key, description, value, previous_value )
     SELECT 'North Readings to OCS','Readings sent to OCS', 0, 0
     WHERE NOT EXISTS (SELECT 1 FROM foglamp.statistics WHERE key = 'North Readings to OCS');

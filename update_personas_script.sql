UPDATE persona SET user_id = (SELECT id FROM "user" WHERE email = 'ameyasharma401@gmail.com') WHERE builtin_persona = false;
UPDATE persona SET voice_id = 'am_echo' WHERE builtin_persona = false AND name != 'Girlfriend';
UPDATE persona SET voice_id = 'af_bella' WHERE builtin_persona = false AND name = 'Girlfriend';

BEGIN;

ALTER TABLE node_wireless ADD COLUMN ssid text DEFAULT '' NOT NULL;

COMMIT;

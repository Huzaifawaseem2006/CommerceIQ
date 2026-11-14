-- Replace the placeholder password before running.
-- This account is for the CommerceIQ application runtime only.

CREATE USER IF NOT EXISTS 'commerceiq_readonly'@'localhost'
  IDENTIFIED BY 'REPLACE_WITH_STRONG_PASSWORD';

GRANT SELECT ON commerceiq.customers TO 'commerceiq_readonly'@'localhost';
GRANT SELECT ON commerceiq.products TO 'commerceiq_readonly'@'localhost';
GRANT SELECT ON commerceiq.orders TO 'commerceiq_readonly'@'localhost';
GRANT SELECT ON commerceiq.order_items TO 'commerceiq_readonly'@'localhost';

FLUSH PRIVILEGES;

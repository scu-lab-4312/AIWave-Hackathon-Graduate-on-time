-- Reference-only contract. This table is owned and populated by the shared CMS.
-- The Medical Lambda is read-only and must never create, truncate, or seed it.
SELECT id, service_vendor_id, name, rate, county_code, zip, county_name,
       district_name, address, phone, business_hours, description,
       upd_time, cre_time, upd_id, cre_id
FROM cms_homepage_service_type_12
LIMIT 0;

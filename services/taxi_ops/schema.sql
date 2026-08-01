-- cms_homepage_service_type_13 is the read-only driver master owned by the shared CMS.
-- The following tables are owned by the Taxi Agent.

CREATE TABLE IF NOT EXISTS agent_taxi_availability (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    driver_id BIGINT NOT NULL,
    start_at DATETIME NOT NULL,
    status ENUM('AVAILABLE', 'BOOKED') NOT NULL DEFAULT 'AVAILABLE',
    UNIQUE KEY uq_agent_taxi_driver_slot (driver_id, start_at),
    INDEX idx_agent_taxi_availability_lookup (driver_id, status, start_at)
);

CREATE TABLE IF NOT EXISTS agent_taxi_bookings (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    booking_code VARCHAR(32) NOT NULL UNIQUE,
    task_id VARCHAR(100) NOT NULL UNIQUE,
    actor_id VARCHAR(100) NOT NULL,
    driver_id BIGINT NOT NULL,
    availability_id BIGINT NOT NULL,
    pickup_city VARCHAR(40) NOT NULL,
    pickup_district VARCHAR(40) NOT NULL,
    destination VARCHAR(240) NOT NULL,
    special_needs VARCHAR(120) NOT NULL,
    status ENUM('REQUESTED', 'CONFIRMED', 'CANCELLED') NOT NULL DEFAULT 'REQUESTED',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_agent_taxi_booking_driver (driver_id, created_at),
    INDEX idx_agent_taxi_booking_slot (availability_id)
);

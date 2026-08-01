-- cms_homepage_service_type_10 is the read-only provider master owned by the shared CMS.
-- The following tables are owned by the Repair Agent and may be initialized idempotently.

CREATE TABLE IF NOT EXISTS agent_repair_provider_services (
    provider_id BIGINT NOT NULL,
    issue_type VARCHAR(60) NOT NULL,
    base_visit_fee INT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (provider_id, issue_type),
    INDEX idx_agent_repair_services_lookup (issue_type, is_active, provider_id)
);

CREATE TABLE IF NOT EXISTS agent_repair_availability (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    provider_id BIGINT NOT NULL,
    start_at DATETIME NOT NULL,
    status ENUM('AVAILABLE', 'BOOKED') NOT NULL DEFAULT 'AVAILABLE',
    UNIQUE KEY uq_agent_repair_provider_slot (provider_id, start_at),
    INDEX idx_agent_repair_availability_lookup (provider_id, status, start_at)
);

CREATE TABLE IF NOT EXISTS agent_repair_price_history (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    seed_key VARCHAR(100) NULL UNIQUE,
    provider_id BIGINT NULL,
    issue_type VARCHAR(60) NOT NULL,
    county_name VARCHAR(40) NOT NULL,
    district_name VARCHAR(40) NOT NULL,
    final_price INT NOT NULL,
    duration_minutes INT NOT NULL,
    completed_at DATETIME NOT NULL,
    INDEX idx_agent_repair_estimate (issue_type, county_name, district_name, completed_at)
);

CREATE TABLE IF NOT EXISTS agent_repair_bookings (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    booking_code VARCHAR(32) NOT NULL UNIQUE,
    task_id VARCHAR(100) NOT NULL UNIQUE,
    actor_id VARCHAR(100) NOT NULL,
    provider_id BIGINT NOT NULL,
    availability_id BIGINT NOT NULL,
    issue_type VARCHAR(60) NOT NULL,
    issue_summary VARCHAR(500) NOT NULL,
    estimate_low INT NOT NULL,
    estimate_high INT NOT NULL,
    status ENUM('REQUESTED', 'CONFIRMED', 'CANCELLED') NOT NULL DEFAULT 'REQUESTED',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_agent_repair_booking_provider (provider_id, created_at),
    INDEX idx_agent_repair_booking_slot (availability_id)
);

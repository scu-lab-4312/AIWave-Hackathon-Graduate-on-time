CREATE TABLE IF NOT EXISTS providers (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(120) NOT NULL,
    city VARCHAR(40) NOT NULL,
    district VARCHAR(40) NOT NULL,
    rating DECIMAL(2,1) NOT NULL,
    completed_jobs INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    INDEX idx_providers_location (city, district, is_active)
);

CREATE TABLE IF NOT EXISTS provider_services (
    provider_id BIGINT NOT NULL,
    issue_type VARCHAR(60) NOT NULL,
    base_visit_fee INT NOT NULL,
    PRIMARY KEY (provider_id, issue_type),
    CONSTRAINT fk_services_provider FOREIGN KEY (provider_id) REFERENCES providers(id)
);

CREATE TABLE IF NOT EXISTS provider_availability (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    provider_id BIGINT NOT NULL,
    start_at DATETIME NOT NULL,
    status ENUM('AVAILABLE', 'BOOKED') NOT NULL DEFAULT 'AVAILABLE',
    CONSTRAINT fk_availability_provider FOREIGN KEY (provider_id) REFERENCES providers(id),
    INDEX idx_availability_lookup (provider_id, status, start_at)
);

CREATE TABLE IF NOT EXISTS repair_events (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    issue_type VARCHAR(60) NOT NULL,
    city VARCHAR(40) NOT NULL,
    district VARCHAR(40) NOT NULL,
    issue_facts_json JSON NOT NULL,
    final_price INT NOT NULL,
    duration_minutes INT NOT NULL,
    completed_at DATETIME NOT NULL,
    INDEX idx_repair_events_estimate (issue_type, city, district, completed_at)
);

CREATE TABLE IF NOT EXISTS bookings (
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
    CONSTRAINT fk_booking_provider FOREIGN KEY (provider_id) REFERENCES providers(id),
    CONSTRAINT fk_booking_availability FOREIGN KEY (availability_id) REFERENCES provider_availability(id)
);

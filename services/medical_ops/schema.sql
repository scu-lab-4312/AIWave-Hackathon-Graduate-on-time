CREATE TABLE IF NOT EXISTS medical_pharmacies (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(120) NOT NULL,
    city VARCHAR(40) NOT NULL,
    district VARCHAR(40) NOT NULL,
    address VARCHAR(240) NOT NULL,
    rating DECIMAL(2,1) NOT NULL,
    pharmacist_name VARCHAR(80) NOT NULL,
    line_id VARCHAR(80) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    INDEX idx_medical_pharmacies_location (city, district, is_active)
);

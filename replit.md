# REFLIV Tracking System

## Overview

A Flask-based web application that parses REFLIV log files to extract and track package shipping information. The system processes uploaded log files containing REFLIV API calls and XML responses, extracting tracking data including reference numbers, shipping statuses, timestamps, and locations. It provides a dashboard for monitoring tracking statistics, searching records, and managing uploaded files.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture
- **Framework**: Flask with SQLAlchemy ORM for database operations
- **Database**: SQLite by default, configurable via DATABASE_URL environment variable
- **File Processing**: Custom log parser that uses regex patterns to extract REFLIV API calls and XML responses
- **Session Management**: Flask sessions with configurable secret key via SESSION_SECRET environment variable
- **File Uploads**: Werkzeug secure filename handling with size limits (16MB max)

### Database Schema
- **ReflixTracking Table**: Stores extracted tracking records with fields for reference numbers, shipping unit references, status, descriptions, timestamps, locations, and source log file information. Includes composite indexes for efficient querying by reference number and timestamp/status combinations.
- **LogFile Table**: Tracks uploaded files with metadata including filename, size, upload timestamp, processing status, and error messages.

### Frontend Architecture
- **Template Engine**: Jinja2 templates with Bootstrap 5 dark theme
- **UI Components**: Responsive design with DataTables for enhanced table functionality
- **Styling**: Custom CSS with Font Awesome icons and Bootstrap framework
- **Navigation**: Multi-page application with dashboard, upload, tracking search, and file management sections

### File Processing Pipeline
- **Upload Validation**: Restricts file types to .txt and .log with size validation
- **Duplicate Prevention**: Checks for previously processed files to avoid reprocessing
- **Regex Parsing**: Uses pattern matching to identify REFLIV API calls and extract reference numbers
- **XML Parsing**: Processes XML responses to extract detailed tracking information including status history
- **Database Storage**: Stores both individual tracking records and file metadata for audit trails

### Configuration Management
- Environment-based configuration for database URL, session secrets, and deployment settings
- ProxyFix middleware for proper handling behind reverse proxies
- Configurable upload directories and file size limits
- Database connection pooling with health checks and automatic reconnection

## External Dependencies

### Python Libraries
- **Flask**: Web framework with SQLAlchemy extension for database operations
- **Werkzeug**: WSGI utilities including ProxyFix middleware and secure filename handling
- **XML Parser**: Built-in xml.etree.ElementTree for parsing REFLIV XML responses

### Frontend Libraries
- **Bootstrap 5**: UI framework with dark theme variant from Replit CDN
- **Font Awesome 6.4.0**: Icon library for UI enhancements
- **DataTables 1.13.7**: Enhanced table functionality with Bootstrap 5 integration

### Database
- **SQLite**: Default database engine with support for PostgreSQL or other databases via DATABASE_URL configuration
- **Connection Pooling**: Configured with 300-second recycle time and pre-ping health checks

### External APIs
- **REFLIV Tracking API**: Integrated via ISS EPG endpoints for real-time package tracking data
- The system parses log files containing calls to: `https://iss.epg.com/iss/v1/clients/{client_id}/tracking/shipment`
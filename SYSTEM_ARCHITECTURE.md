# PulseQ Backend - System Architecture Document

**Version:** 1.0.0  
**Last Updated:** May 24, 2026  
**Status:** Production Ready

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Tech Stack](#2-tech-stack)
3. [Project Structure](#3-project-structure)
4. [Database Schema](#4-database-schema)
5. [API Reference](#5-api-reference)
6. [Service Layer Map](#6-service-layer-map)
7. [Authentication & Roles](#7-authentication--roles)
8. [Page to API Linkage](#8-page-to-api-linkage)
9. [Background Services](#9-background-services)
10. [Third Party Integrations](#10-third-party-integrations)
11. [Error Handling](#11-error-handling)
12. [Deployment](#12-deployment)

---

## 1. System Overview

### 1.1 What This System Does

PulseQ is a comprehensive healthcare appointment management system that enables patients to book appointments with doctors at hospitals, manage queues, receive real-time notifications, and handle payments. The system supports multiple user roles including patients, doctors, receptionists, administrators, and pharmacy staff.

**Key Features:**
- Smart token-based queue management with real-time position tracking
- WhatsApp and SMS notifications for appointment updates
- Doctor availability management and leave handling
- Pharmacy inventory management and invoicing
- AI-powered queue prediction and optimization
- Multi-hospital support with role-based access control
- Payment processing with wallet and refund management
- Medical record tracking and patient history

### 1.2 User Roles

| Role | Description | Primary Access |
|------|-------------|----------------|
| **Patient** | End users who book appointments, manage tokens, and receive notifications | Patient App, Public APIs |
| **Doctor** | Healthcare providers who manage their queues, consult patients, and update availability | Doctor Portal |
| **Receptionist** | Hospital staff who manage appointments, tokens, and patient flow on behalf of hospital | Reception Portal |
| **Admin** | System administrators who manage hospitals, doctors, and system-wide settings | Admin Dashboard |
| **Pharmacy** | Pharmacy staff who manage inventory, process prescriptions, and handle sales | Pharmacy Portal |

### 1.3 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │ Patient  │  │ Doctor  │  │Reception │  │ Pharmacy │         │
│  │   App    │  │ Portal  │  │  Portal  │  │  Portal  │         │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘         │
│       │             │             │             │                 │
└───────┼─────────────┼─────────────┼─────────────┼─────────────────┘
        │             │             │             │
        └─────────────┴─────────────┴─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │   API GATEWAY (FastAPI)   │
        │  - CORS Middleware         │
        │  - Performance Monitoring  │
        │  - Authentication         │
        │  - Exception Handlers      │
        └─────────────┬─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │     ROUTE LAYER           │
        │  - Auth Routes            │
        │  - Token Routes           │
        │  - Hospital Routes        │
        │  - Doctor Routes          │
        │  - Pharmacy Routes        │
        │  - Queue Routes           │
        │  - Payment Routes         │
        └─────────────┬─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │    SERVICE LAYER          │
        │  - Queue Management       │
        │  - Notification Service   │
        │  - Token Service          │
        │  - Doctor Leave Service   │
        │  - Pharmacy Service       │
        │  - AI Engine              │
        └─────────────┬─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │    DATA LAYER            │
        │  ┌──────────┐  ┌──────┐  │
        │  │PostgreSQL│  │Redis │  │
        │  │  (Primary)│  │(Cache)│  │
        │  └──────────┘  └──────┘  │
        │  ┌──────────┐  ┌──────┐  │
        │  │ Firebase  │  │Cloud │  │
        │  │ (Legacy) │  │R2/S3 │  │
        │  └──────────┘  └──────┘  │
        └─────────────┬─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │   EXTERNAL INTEGRATIONS   │
        │  - Twilio WhatsApp        │
        │  - POS System             │
        │  - OpenStreetMap          │
        │  - AI/ML Engine           │
        └───────────────────────────┘
```

---

## 2. Tech Stack

| Technology | Purpose | Version/Details |
|------------|---------|-----------------|
| **FastAPI** | Web Framework | Latest, Python 3.9+ |
| **PostgreSQL** | Primary Database | DigitalOcean Managed DB |
| **SQLAlchemy** | ORM | 2.0+ with async support |
| **Alembic** | Database Migrations | Integrated |
| **Pydantic** | Data Validation | v2.0+ |
| **Firebase Firestore** | Legacy Database (being migrated) | Google Cloud |
| **Twilio** | WhatsApp & SMS Notifications | API Integration |
| **Redis/Upstash** | Caching & Pub/Sub | Serverless Redis |
| **APScheduler** | Job Scheduling | AsyncIOScheduler |
| **XGBoost** | AI/ML Queue Prediction | Python ML Library |
| **Cloudflare R2** | Object Storage | S3-compatible |
| **bcrypt + SHA-256** | Password Hashing | Security |
| **JWT (python-jose)** | Authentication Tokens | HS256 Algorithm |
| **httpx** | Async HTTP Client | External API calls |
| **OpenStreetMap** | Geolocation Services | Overpass API, Nominatim |

---

## 3. Project Structure

```
PulseQ_Backend/
├── backend/
│   ├── main.py                          # FastAPI application entry point
│   ├── worker.py                       # Background worker processes
│   ├── requirements.txt                 # Python dependencies
│   ├── Dockerfile                      # Container configuration
│   ├── Procfile                        # Process configuration (Heroku/Render)
│   ├── alembic/                        # Database migrations
│   │   ├── versions/                   # Migration scripts
│   │   └── alembic.ini                 # Alembic configuration
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py                   # Application configuration
│   │   ├── config_env.py               # Environment-specific config
│   │   ├── database.py                 # Database connection & session management
│   │   ├── db_models.py                # SQLAlchemy ORM models (PostgreSQL)
│   │   ├── models.py                   # Pydantic schemas
│   │   ├── security.py                 # JWT authentication & authorization
│   │   ├── exceptions.py               # Custom exception classes
│   │   ├── logger.py                   # Logging configuration
│   │   ├── templates.py                # WhatsApp template mappings
│   │   ├── routes/                     # API route handlers
│   │   │   ├── auth.py                 # Authentication endpoints
│   │   │   ├── auth_otp.py             # OTP-based authentication
│   │   │   ├── hospitals.py            # Hospital management
│   │   │   ├── doctors.py              # Doctor management
│   │   │   ├── tokens.py               # Token generation & management
│   │   │   ├── tokens_listing.py       # Token listing endpoints
│   │   │   ├── tokens_idempotent.py    # Idempotent token operations
│   │   │   ├── token_alias.py          # Frontend-friendly token routes
│   │   │   ├── queue.py                # Queue management
│   │   │   ├── payments.py             # Payment processing
│   │   │   ├── dashboard.py            # Patient dashboard
│   │   │   ├── profile.py              # User profile management
│   │   │   ├── patient.py              # Patient-specific actions
│   │   │   ├── consultation.py         # Consultation flow
│   │   │   ├── realtime.py             # Real-time updates
│   │   │   ├── portal.py               # Staff portal endpoints
│   │   │   ├── pharmacy.py             # Pharmacy management
│   │   │   ├── pos.py                  # POS system integration
│   │   │   ├── reception.py            # Reception desk integration
│   │   │   ├── ratings.py              # Doctor ratings
│   │   │   ├── refunds.py              # Refund processing
│   │   │   ├── support.py              # Support tickets
│   │   │   ├── medical_records.py      # Medical record management
│   │   │   ├── whatsapp_webhook.py     # WhatsApp webhook handlers
│   │   │   ├── health.py               # Health check endpoints
│   │   │   ├── ai.py                   # AI endpoints
│   │   │   ├── ml.py                   # ML endpoints
│   │   │   └── notifications.py        # Notification endpoints
│   │   ├── services/                   # Business logic layer
│   │   │   ├── queue_management_service.py    # Queue state & logic
│   │   │   ├── notification_service.py        # WhatsApp/SMS notifications
│   │   │   ├── whatsapp_service.py            # WhatsApp template sending
│   │   │   ├── token_service.py               # Token generation logic
│   │   │   ├── doctor_leave_service.py        # Doctor leave handling
│   │   │   ├── confirmation_scheduler.py      # Appointment confirmation
│   │   │   ├── message_scheduler.py           # Message scheduling
│   │   │   ├── pharmacy_inventory_service.py  # Pharmacy inventory
│   │   │   ├── refund_service.py              # Refund processing
│   │   │   ├── fee_calculator.py              # Fee calculations
│   │   │   ├── ai_engine.py                   # AI/ML prediction engine
│   │   │   ├── cache_service.py               # Caching layer
│   │   │   ├── redis_service.py               # Redis/Upstash integration
│   │   │   ├── storage_service.py             # Cloudflare R2/S3 storage
│   │   │   ├── sync_service.py                # POS synchronization
│   │   │   ├── slot_booking_service.py        # Slot allocation
│   │   │   ├── app_scheduler.py               # APScheduler wrapper
│   │   │   ├── notification_scheduler_client.py # External notification client
│   │   │   ├── go_pos_service.py              # Go POS service integration
│   │   │   └── voice_service.py               # Voice notification service
│   │   ├── middleware/                 # Custom middleware
│   │   │   └── performance.py         # Request timing & monitoring
│   │   ├── utils/                     # Utility functions
│   │   │   ├── responses.py           # Standard response helpers
│   │   │   ├── state.py               # State transition validation
│   │   │   ├── mrn.py                 # MRN generation
│   │   │   └── date_utils.py          # Date/time utilities
│   │   ├── controllers/               # Additional controllers
│   │   ├── data/                      # Data files
│   │   └── schemas/                   # Additional schemas
│   ├── db_automation/                 # Database automation module
│   │   ├── app.py                     # Pharmacy automation app
│   │   ├── config.py                  # Automation config
│   │   ├── database.py                # Database connection for automation
│   │   ├── models.py                  # Automation ORM models
│   │   └── services.py                # Automation CRUD services
│   ├── node-notification-service/     # Node.js notification service
│   │   ├── package.json
│   │   ├── server.js
│   │   └── whatsapp/
│   └── scripts/                       # Utility scripts
├── frontend/                          # Frontend application (React/Angular)
├── .env                               # Environment variables
├── .env.template                      # Environment template
├── .gitignore
├── README.md
└── ROUTING_ANALYSIS.md                # API routing documentation
```

---

## 4. Database Schema

### 4.1 Core Tables (PostgreSQL)

#### Users Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | User UUID |
| name | String(100) | NO | - | - | Full name |
| email | String(255) | YES | UNIQUE | - | Email address |
| phone | String(20) | YES | UNIQUE | - | Phone number |
| password_hash | String(255) | NO | - | - | SHA-256 + bcrypt hash |
| role | String(20) | NO | INDEX | - | PATIENT, DOCTOR, ADMIN, RECEPTIONIST, PHARMACY |
| hospital_id | String | YES | INDEX | hospitals.id | Associated hospital for staff |
| location_access | Boolean | NO | - | - | Location permission flag |
| date_of_birth | String(20) | YES | - | - | Date of birth |
| gender | String(20) | YES | - | - | Gender |
| address | String(500) | YES | - | - | Physical address |
| mrn_by_hospital | JSON | NO | - | - | MRN mapping per hospital |
| avatar_url | String(500) | YES | - | - | Profile picture URL |
| avatar_mime | String(100) | YES | - | - | Avatar MIME type |
| avatar_updated_at | DateTime | YES | - | - | Avatar last updated |
| created_at | DateTime | NO | INDEX | - | Account creation timestamp |
| updated_at | DateTime | YES | - | - | Last update timestamp |

**Relationships:**
- `tokens` → One-to-Many with Token
- `activities` → One-to-Many with ActivityLog

---

#### Hospitals Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | Hospital UUID |
| name | String(200) | NO | - | - | Hospital name |
| address | String(500) | NO | - | - | Physical address |
| city | String(100) | NO | - | - | City |
| state | String(100) | NO | - | - | State/Province |
| phone | String(20) | NO | - | - | Contact phone |
| email | String(255) | YES | - | - | Contact email |
| rating | Float | YES | - | - | Average rating (0-5) |
| review_count | Integer | NO | - | - | Total review count |
| status | String(20) | NO | INDEX | - | OPEN, CLOSED, MAINTENANCE |
| specializations | JSON | NO | - | - | List of specializations |
| latitude | Float | YES | - | - | GPS latitude |
| longitude | Float | YES | - | - | GPS longitude |
| created_at | DateTime | NO | INDEX | - | Creation timestamp |
| updated_at | DateTime | YES | - | - | Last update timestamp |

**Relationships:**
- `doctors` → One-to-Many with Doctor

---

#### Doctors Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | Doctor UUID |
| user_id | String | YES | INDEX | users.id | Linked user account |
| name | String(100) | NO | INDEX | - | Doctor name |
| specialization | String(100) | NO | INDEX | - | Medical specialization |
| subcategory | String(100) | YES | INDEX | - | Detailed subcategory |
| hospital_id | String | NO | INDEX | hospitals.id |所属医院 |
| email | String(255) | YES | - | - | Contact email |
| phone | String(20) | YES | - | - | Contact phone |
| rating | Float | YES | - | - | Average rating |
| review_count | Integer | NO | - | - | Total review count |
| consultation_fee | Float | NO | - | - | Base consultation fee |
| session_fee | Float | YES | - | - | Per-session fee (optional) |
| has_session | Boolean | NO | - | - | Session-based pricing flag |
| pricing_type | String(20) | NO | - | - | standard, session_based |
| status | String(20) | NO | INDEX | - | AVAILABLE, BUSY, OFFLINE, ON_LEAVE |
| available_days | JSON | NO | - | - | Available days list |
| start_time | String(10) | NO | - | - | Clinic start time (HH:MM) |
| end_time | String(10) | NO | - | - | Clinic end time (HH:MM) |
| avatar_initials | String(10) | YES | - | - | Avatar initials |
| patients_per_day | Integer | NO | - | - | Daily patient limit |
| created_at | DateTime | NO | INDEX | - | Creation timestamp |
| updated_at | DateTime | YES | - | - | Last update timestamp |

**Relationships:**
- `hospital` → Many-to-One with Hospital
- `tokens` → One-to-Many with Token

---

#### Tokens Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | Token UUID |
| patient_id | String | NO | INDEX | users.id | Patient user ID |
| doctor_id | String | NO | INDEX | doctors.id | Doctor ID |
| hospital_id | String | NO | INDEX | hospitals.id | Hospital ID |
| mrn | String(50) | YES | INDEX | - | Medical Record Number |
| token_number | Integer | NO | - | - | Sequential token number |
| hex_code | String(20) | NO | INDEX | - | Unique hex code |
| display_code | String(20) | YES | - | - | Human-readable code |
| appointment_date | DateTime | NO | INDEX | - | Appointment datetime |
| status | String(20) | NO | INDEX | - | PENDING, WAITING, CONFIRMED, IN_QUEUE, IN_PROGRESS, COMPLETED, CANCELLED, RESCHEDULED, SKIPPED |
| payment_status | String(20) | NO | INDEX | - | PENDING, PAID, UNPAID, FAILED, CANCELLED |
| payment_method | String(20) | YES | - | - | ONLINE, RECEPTION |
| queue_position | Integer | YES | - | - | Current queue position |
| total_queue | Integer | YES | - | - | Total queue size |
| estimated_wait_time | Integer | YES | - | - | Wait time in minutes |
| consultation_fee | Float | YES | - | - | Consultation fee |
| session_fee | Float | YES | - | - | Session fee |
| total_fee | Float | YES | - | - | Total fee |
| department | String(100) | YES | INDEX | - | Department name |
| pending_skip_task_id | String(255) | YES | - | - | Scheduled skip task ID |
| skipped_at | DateTime | YES | - | - | Skip timestamp |
| idempotency_key | String(255) | YES | INDEX | - | Idempotency key |
| created_at | DateTime | NO | INDEX | - | Creation timestamp |
| updated_at | DateTime | YES | - | - | Last update timestamp |
| doctor_name | String(100) | YES | - | - | Snapshot: doctor name |
| doctor_specialization | String(100) | YES | - | - | Snapshot: specialization |
| doctor_avatar_initials | String(10) | YES | - | - | Snapshot: avatar initials |
| hospital_name | String(200) | YES | - | - | Snapshot: hospital name |
| patient_name | String(100) | YES | - | - | Snapshot: patient name |
| patient_phone | String(20) | YES | - | - | Snapshot: patient phone |
| patient_age | Integer | YES | - | - | Snapshot: patient age |
| patient_gender | String(20) | YES | - | - | Snapshot: patient gender |
| reason_for_visit | Text | YES | - | - | Visit reason |
| consultation_notes | Text | YES | - | - | Consultation notes |
| queue_opt_in | Boolean | NO | - | - | Queue notification opt-in |
| queue_opted_in_at | DateTime | YES | - | - | Opt-in timestamp |
| confirmed | Boolean | NO | - | - | Confirmation flag |
| confirmation_status | String(50) | YES | - | - | Confirmation status |
| confirmed_at | DateTime | YES | - | - | Confirmation timestamp |
| cancelled_at | DateTime | YES | - | - | Cancellation timestamp |
| called_at | DateTime | YES | - | - | Called timestamp |
| started_at | DateTime | YES | - | - | Consultation start |
| completed_at | DateTime | YES | - | - | Consultation end |
| duration_minutes | Float | YES | - | - | Consultation duration |
| doctor_unavailable | Boolean | NO | - | - | Doctor unavailable flag |
| doctor_unavailable_reason | String(255) | YES | - | - | Unavailability reason |
| leave_action | String(100) | YES | - | - | Leave action taken |
| suggested_doctor_id | String | YES | - | - | Suggested replacement doctor |
| suggested_doctor_name | String(100) | YES | - | - | Suggested doctor name |
| rescheduled_at | DateTime | YES | - | - | Reschedule timestamp |
| is_rated | Boolean | NO | - | - | Rating submitted flag |
| rating | Integer | YES | - | - | Patient rating (1-5) |

**Relationships:**
- `patient` → Many-to-One with User
- `doctor` → Many-to-One with Doctor
- `payments` → One-to-Many with Payment

---

#### Payments Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | Payment UUID |
| token_id | String | NO | - | tokens.id | Associated token |
| amount | Float | NO | - | - | Payment amount |
| method | String(20) | NO | - | - | ONLINE, RECEPTION |
| status | String(20) | NO | - | - | PENDING, PAID, UNPAID, FAILED, CANCELLED |
| transaction_id | String(255) | YES | - | - | External transaction ID |
| created_at | DateTime | NO | - | - | Creation timestamp |
| updated_at | DateTime | YES | - | - | Last update timestamp |

**Relationships:**
- `token` → Many-to-One with Token

---

#### ActivityLog Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | Activity UUID |
| user_id | String | NO | - | users.id | User who performed action |
| activity_type | String(50) | NO | - | - | Activity type enum |
| description | Text | NO | - | - | Activity description |
| meta_data | JSON | YES | - | - | Additional metadata |
| created_at | DateTime | NO | - | - | Creation timestamp |
| updated_at | DateTime | YES | - | - | Last update timestamp |

**Relationships:**
- `user` → Many-to-One with User

---

#### Queue Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | Queue UUID |
| doctor_id | String | NO | - | doctors.id | Associated doctor |
| current_token | Integer | YES | - | - | Current token number |
| waiting_patients | Integer | NO | - | - | Waiting patient count |
| estimated_wait_time_minutes | Integer | YES | - | - | Estimated wait time |
| people_ahead | Integer | NO | - | - | People ahead in queue |
| total_queue | Integer | NO | - | - | Total queue size |
| paused | Boolean | NO | - | - | Queue paused flag |
| queue_paused | Boolean | NO | - | - | Queue paused flag (legacy) |
| queue_pause_reason | String(255) | YES | - | - | Pause reason |
| updated_at | DateTime | YES | - | - | Last update timestamp |

---

#### PharmacyMedicine Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | Medicine UUID |
| product_id | Integer | NO | INDEX | - | Product ID |
| batch_no | String(50) | NO | INDEX | - | Batch number |
| name | String(200) | NO | INDEX | - | Medicine name |
| generic_name | String(200) | YES | INDEX | - | Generic name |
| type | String(100) | YES | - | - | Medicine type |
| distributor | String(200) | YES | - | - | Distributor |
| purchase_price | Float | NO | - | - | Purchase price |
| selling_price | Float | NO | - | - | Selling price |
| stock_unit | String(50) | YES | - | - | Stock unit |
| quantity | Integer | NO | INDEX | - | Stock quantity |
| expiration_date | DateTime | YES | INDEX | - | Expiration date |
| manufacture_date | DateTime | YES | - | - | Manufacture date |
| category | String(100) | YES | INDEX | - | Category |
| sub_category | String(100) | YES | INDEX | - | Subcategory |
| hospital_id | String | YES | INDEX | hospitals.id | Hospital ID |
| is_deleted | Boolean | NO | INDEX | - | Soft delete flag |
| deleted_at | DateTime | YES | - | - | Deletion timestamp |
| created_at | DateTime | NO | - | - | Creation timestamp |
| updated_at | DateTime | YES | INDEX | - | Last update timestamp |

**Composite Index:** `ix_pharmacy_medicines_hospital_updated` on (hospital_id, updated_at)

---

#### PharmacyInvoice Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | Invoice UUID |
| invoice_number | String | NO | UNIQUE INDEX | - | Invoice number |
| customer_id | String | YES | - | - | Customer ID |
| customer_name | String | NO | - | - | Customer name |
| status | String | NO | INDEX | - | Invoice status |
| payment_method | String | NO | - | - | Payment method |
| subtotal | Float | NO | - | - | Subtotal |
| discount | Float | NO | - | - | Discount amount |
| discount_percent | Float | NO | - | - | Discount percentage |
| tax | Float | NO | - | - | Tax amount |
| total | Float | NO | - | - | Total amount |
| amount_paid | Float | NO | - | - | Amount paid |
| balance_due | Float | NO | - | - | Balance due |
| notes | Text | YES | - | - | Invoice notes |
| hospital_id | String | YES | INDEX | hospitals.id | Hospital ID |
| created_by | String | YES | - | - | Creator ID |
| is_deleted | Boolean | NO | - | - | Soft delete flag |
| deleted_at | DateTime | YES | - | - | Deletion timestamp |
| created_at | DateTime | NO | - | - | Creation timestamp |
| updated_at | DateTime | YES | - | - | Last update timestamp |

---

#### PharmacyInvoiceItem Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | Item UUID |
| invoice_id | String | NO | INDEX | pharmacy_invoices.id | Parent invoice |
| medicine_id | String | YES | - | - | Medicine ID |
| product_id | Integer | YES | - | - | Product ID |
| product_name | String | NO | - | - | Product name |
| product_code | String | YES | - | - | Product code |
| quantity | Float | NO | - | - | Quantity |
| unit_price | Float | NO | - | - | Unit price |
| discount | Float | NO | - | - | Discount |
| total | Float | NO | - | - | Line total |
| created_at | DateTime | NO | - | - | Creation timestamp |

---

#### DoctorRating Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | Rating UUID |
| token_id | String | NO | INDEX | tokens.id | Associated token |
| doctor_id | String | NO | INDEX | doctors.id | Rated doctor |
| patient_id | String | NO | INDEX | users.id | Rating patient |
| rating | Integer | NO | - | - | Rating (1-5) |
| review | Text | YES | - | - | Review text |
| patient_name | String(100) | YES | - | - | Snapshot: patient name |
| patient_avatar_initials | String(10) | YES | - | - | Snapshot: patient initials |
| appointment_date | DateTime | YES | - | - | Snapshot: appointment date |
| created_at | DateTime | NO | - | - | Creation timestamp |
| updated_at | DateTime | YES | - | - | Last update timestamp |

**Unique Constraint:** `uq_token_patient_rating` on (token_id, patient_id)

---

#### Wallet Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | Wallet UUID |
| user_id | String | NO | UNIQUE | users.id | Owner user ID |
| balance | Float | NO | - | - | Wallet balance |
| currency | String(10) | NO | - | - | Currency code |
| created_at | DateTime | NO | - | - | Creation timestamp |
| updated_at | DateTime | YES | - | - | Last update timestamp |

---

#### Refund Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | Refund UUID |
| user_id | String | NO | - | users.id | User ID |
| token_id | String | NO | - | tokens.id | Associated token |
| amount | Float | NO | - | - | Refund amount |
| status | String(20) | NO | - | - | PENDING, PROCESSING, COMPLETED, FAILED |
| method | String(50) | NO | - | - | Refund method |
| reason | String(255) | YES | - | - | Refund reason |
| transaction_id | String(255) | YES | - | - | Transaction ID |
| created_at | DateTime | NO | - | - | Creation timestamp |
| updated_at | DateTime | YES | - | - | Last update timestamp |

---

#### SupportTicket Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | Ticket UUID |
| user_id | String | NO | - | users.id | User ID |
| subject | String(255) | NO | - | - | Ticket subject |
| description | Text | NO | - | - | Ticket description |
| category | String(50) | NO | - | - | Ticket category |
| priority | String(20) | NO | - | - | Priority level |
| status | String(20) | NO | - | - | Ticket status |
| created_at | DateTime | NO | - | - | Creation timestamp |
| updated_at | DateTime | YES | - | - | Last update timestamp |

---

#### OTPVerification Table
| Column | Type | Nullable | Index | FK | Description |
|--------|------|----------|-------|-----|-------------|
| id | String | NO | PK | - | OTP UUID |
| phone | String | NO | - | - | Phone number |
| otp | String | NO | - | - | OTP code |
| is_used | Boolean | NO | - | - | Used flag |
| expires_at | DateTime | NO | - | - | Expiration time |
| created_at | DateTime | NO | - | - | Creation timestamp |

---

#### Additional Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `HospitalSequence` | MRN sequence per hospital | hospital_id, mrn_seq |
| `Department` | Hospital departments | name, hospital_id |
| `QuickAction` | User quick actions | user_id, action_type |
| `MedicalRecord` | Patient medical records | user_id, file_path |
| `IdempotencyRecord` | Idempotency tracking | user_id, key, action |
| `PharmacySale` | Pharmacy sales records | hospital_id, patient_id, medicine_id |

---

## 5. API Reference

### 5.1 Authentication Endpoints

| Method | URL Path | Auth Roles | Request Body | Response | Description | Linked Frontend Page |
|--------|-----------|------------|-------------|----------|-------------|---------------------|
| POST | `/api/v1/auth/register` | Public | UserCreate | UserResponse | Register new user | Signup Page |
| POST | `/api/v1/auth/login` | Public | LoginRequest | Token | User login | Login Page |
| GET | `/api/v1/auth/check-phone/{phone}` | Public | - | PhoneCheckResponse | Check if phone exists | Signup Form |
| POST | `/api/v1/auth/otp/send` | Public | OTPRequest | SuccessResponse | Send OTP via WhatsApp | OTP Login |
| POST | `/api/v1/auth/otp/verify` | Public | OTPVerifyRequest | TokenResponse | Verify OTP code | OTP Login |
| POST | `/api/v1/auth/refresh` | Public | RefreshTokenRequest | Token | Refresh access token | Background Refresh |

---

### 5.2 Hospital Endpoints

| Method | URL Path | Auth Roles | Request Body | Response | Description | Linked Frontend Page |
|--------|-----------|------------|-------------|----------|-------------|---------------------|
| GET | `/api/v1/public/hospitals/` | Public | - | List[HospitalResponse] | List all hospitals | Hospital Search |
| POST | `/api/v1/public/hospitals/` | Admin/Receptionist | HospitalCreate | HospitalResponse | Create hospital | Admin Dashboard |
| GET | `/api/v1/public/hospitals/{hospital_id}` | Public | - | HospitalResponse | Get hospital by ID | Hospital Details |
| GET | `/api/v1/public/hospitals/nearby` | Public | lat, lng, radius | HospitalSearchResponse | Find nearby hospitals | Nearby Hospitals |
| GET | `/api/v1/public/hospitals/open` | Public | city, limit | HospitalSearchResponse | Get open hospitals | Hospital Search |
| GET | `/api/v1/public/hospitals/search` | Public | query, city | HospitalSearchResponse | Search hospitals | Hospital Search |
| GET | `/api/v1/public/hospitals/search-unified` | Public | query, lat, lng | HospitalUnifiedSearchResponse | Unified DB+OSM search | Hospital Search |
| GET | `/api/v1/public/hospitals/{hospital_id}/doctors` | Public | - | DoctorSearchResponse | Get hospital doctors | Hospital Details |
| GET | `/api/v1/public/hospitals/{hospital_id}/categories` | Public | - | CategoriesResponse | Get hospital categories | Hospital Details |

---

### 5.3 Doctor Endpoints

| Method | URL Path | Auth Roles | Request Body | Response | Description | Linked Frontend Page |
|--------|-----------|------------|-------------|----------|-------------|---------------------|
| GET | `/api/v1/public/doctors/` | Public | hospital_id, limit | List[DoctorResponse] | List doctors | Doctor Search |
| GET | `/api/v1/public/doctors/{doctor_id}` | Public | - | DoctorResponse | Get doctor by ID | Doctor Details |
| GET | `/api/v1/public/doctors/hospital/{hospital_id}` | Public | - | DoctorSearchResponse | Get doctors by hospital | Hospital Details |
| GET | `/api/v1/public/doctors/category/{category}` | Public | - | DoctorSearchResponse | Get doctors by category | Doctor Search |
| POST | `/api/v1/staff/doctors/` | Admin/Receptionist | DoctorCreate | DoctorResponse | Create doctor | Admin Dashboard |
| PATCH | `/api/v1/staff/doctors/{doctor_id}` | Admin/Receptionist | DoctorUpdate | DoctorResponse | Update doctor | Admin Dashboard |
| DELETE | `/api/v1/staff/doctors/{doctor_id}` | Admin | - | SuccessResponse | Delete doctor | Admin Dashboard |
| PATCH | `/api/v1/staff/doctors/{doctor_id}/status` | Admin/Receptionist | StatusUpdate | DoctorResponse | Update doctor status | Doctor Portal |
| GET | `/api/v1/staff/doctors/{doctor_id}/availability` | Doctor | - | AvailabilityResponse | Get doctor availability | Doctor Portal |

---

### 5.4 Token Endpoints

| Method | URL Path | Auth Roles | Request Body | Response | Description | Linked Frontend Page |
|--------|-----------|------------|-------------|----------|-------------|---------------------|
| POST | `/api/v1/patient/tokens/generate` | Patient | SmartTokenGenerateRequest | SmartTokenResponse | Generate new token | Book Appointment |
| POST | `/api/v1/patient/tokens/generate/details` | Patient | SmartTokenGenerateRequest | TokenDetailsResponse | Generate with details | Book Appointment |
| GET | `/api/v1/patient/tokens/{token_id}` | Patient | - | SmartTokenResponse | Get token by ID | Token Details |
| GET | `/api/v1/patient/tokens/` | Patient | status, limit | List[SmartTokenResponse] | List user tokens | My Tokens |
| PATCH | `/api/v1/patient/tokens/{token_id}` | Patient | TokenUpdate | SmartTokenResponse | Update token | Token Details |
| DELETE | `/api/v1/patient/tokens/{token_id}/cancel` | Patient | CancellationRequest | CancellationResponse | Cancel token | My Tokens |
| POST | `/api/v1/patient/tokens/{token_id}/cancel` | Patient | CancellationRequest (POST) | CancellationResponse | Cancel token (POST) | My Tokens |
| GET | `/api/v1/patient/tokens/list/hospital/{hospital_id}` | Staff | limit | List[Token] | List hospital tokens | Reception Portal |
| POST | `/api/v1/patient/tokens/secure/create` | Patient | SmartTokenCreate | SmartTokenResponse | Idempotent create | Book Appointment |

---

### 5.5 Queue Endpoints

| Method | URL Path | Auth Roles | Request Body | Response | Description | Linked Frontend Page |
|--------|-----------|------------|-------------|----------|-------------|---------------------|
| GET | `/api/v1/patient/queue/doctor/{doctor_id}` | Public | - | QueueResponse | Get queue status | Queue Status |
| POST | `/api/v1/patient/queue/advance` | Doctor/Receptionist | AdvanceRequest | QueueResponse | Advance queue | Doctor Portal |
| POST | `/api/v1/patient/queue/pause` | Doctor/Receptionist | PauseRequest | QueueResponse | Pause queue | Doctor Portal |
| POST | `/api/v1/patient/queue/resume` | Doctor/Receptionist | - | QueueResponse | Resume queue | Doctor Portal |
| GET | `/api/v1/patient/queue/position/{token_id}` | Patient | - | PositionResponse | Get queue position | Token Details |

---

### 5.6 Payment Endpoints

| Method | URL Path | Auth Roles | Request Body | Response | Description | Linked Frontend Page |
|--------|-----------|------------|-------------|----------|-------------|---------------------|
| POST | `/api/v1/patient/payments/create` | Patient | PaymentCreate | PaymentResponse | Create payment | Payment Page |
| GET | `/api/v1/patient/payments/{payment_id}` | Patient | - | PaymentResponse | Get payment by ID | Payment History |
| GET | `/api/v1/patient/payments/token/{token_id}` | Patient | - | List[PaymentResponse] | Get token payments | Token Details |
| POST | `/api/v1/patient/payments/{payment_id}/refund` | Patient | RefundRequest | RefundResponse | Request refund | Payment History |

---

### 5.7 Patient Portal Endpoints

| Method | URL Path | Auth Roles | Request Body | Response | Description | Linked Frontend Page |
|--------|-----------|------------|-------------|----------|-------------|---------------------|
| GET | `/api/v1/patient/dashboard` | Patient | - | DashboardData | Get patient dashboard | Patient Dashboard |
| GET | `/api/v1/patient/profile` | Patient | - | UserResponse | Get user profile | Profile Page |
| PATCH | `/api/v1/patient/profile` | Patient | ProfileUpdate | UserResponse | Update profile | Profile Page |
| POST | `/api/v1/patient/actions/location` | Patient | LocationUpdate | SuccessResponse | Update location | Settings |
| GET | `/api/v1/patient/actions/activities` | Patient | limit | List[ActivityLog] | Get activities | Activity History |

---

### 5.8 Staff Portal Endpoints

| Method | URL Path | Auth Roles | Request Body | Response | Description | Linked Frontend Page |
|--------|-----------|------------|-------------|----------|-------------|---------------------|
| GET | `/api/v1/staff/portal/notifications` | Staff | limit | List[Notification] | Get notifications | Staff Portal |
| POST | `/api/v1/staff/portal/notifications/read` | Staff | NotificationIds | SuccessResponse | Mark as read | Staff Portal |
| GET | `/api/v1/staff/portal/tokens/active` | Staff | doctor_id | List[Token] | Get active tokens | Reception Portal |
| GET | `/api/v1/staff/realtime/queue/{doctor_id}` | Staff | - | QueueStatus | Get real-time queue | Doctor Portal |
| POST | `/api/v1/staff/consultation/start` | Doctor | ConsultationStart | ConsultationResponse | Start consultation | Doctor Portal |
| POST | `/api/v1/staff/consultation/end` | Doctor | ConsultationEnd | ConsultationResponse | End consultation | Doctor Portal |

---

### 5.9 Pharmacy Endpoints

| Method | URL Path | Auth Roles | Request Body | Response | Description | Linked Frontend Page |
|--------|-----------|------------|-------------|----------|-------------|---------------------|
| GET | `/api/v1/public/pharmacy/medicines` | Public | hospital_id, search | List[PharmacyMedicine] | Search medicines | Pharmacy Search |
| GET | `/api/v1/staff/pharmacy/inventory` | Pharmacy | hospital_id | List[PharmacyMedicine] | Get inventory | Pharmacy Portal |
| POST | `/api/v1/staff/pharmacy/inventory` | Pharmacy | MedicineCreate | PharmacyMedicine | Add medicine | Pharmacy Portal |
| PATCH | `/api/v1/staff/pharmacy/inventory/{id}` | Pharmacy | MedicineUpdate | PharmacyMedicine | Update medicine | Pharmacy Portal |
| DELETE | `/api/v1/staff/pharmacy/inventory/{id}` | Pharmacy | - | SuccessResponse | Delete medicine | Pharmacy Portal |
| POST | `/api/v1/staff/pharmacy/invoices` | Pharmacy | InvoiceCreate | PharmacyInvoice | Create invoice | Pharmacy Portal |
| GET | `/api/v1/staff/pharmacy/invoices` | Pharmacy | hospital_id | List[PharmacyInvoice] | List invoices | Pharmacy Portal |
| GET | `/api/v1/staff/pharmacy/invoices/{invoice_id}` | Pharmacy | - | PharmacyInvoice | Get invoice | Pharmacy Portal |

---

### 5.10 External Integration Endpoints

| Method | URL Path | Auth Roles | Request Body | Response | Description | Linked Frontend Page |
|--------|-----------|------------|-------------|----------|-------------|---------------------|
| POST | `/api/v1/external/pos/webhook` | Public (Secret) | POSWebhook | SuccessResponse | POS system webhook | POS System |
| GET | `/api/v1/external/pos/sync` | Admin | - | SyncStatus | Trigger POS sync | Admin Dashboard |
| POST | `/api/v1/external/reception/webhook` | Public (Secret) | ReceptionWebhook | SuccessResponse | Reception webhook | Reception System |

---

### 5.11 Webhook Endpoints

| Method | URL Path | Auth Roles | Request Body | Response | Description | Linked Frontend Page |
|--------|-----------|------------|-------------|----------|-------------|---------------------|
| POST | `/api/v1/webhooks/whatsapp` | Public (Twilio) | WhatsAppWebhook | TwilioResponse | WhatsApp message webhook | WhatsApp Service |

---

### 5.12 AI/ML Endpoints

| Method | URL Path | Auth Roles | Request Body | Response | Description | Linked Frontend Page |
|--------|-----------|------------|-------------|----------|-------------|---------------------|
| POST | `/api/v1/ai/ml/predict` | Admin | PredictionRequest | PredictionResponse | Queue prediction | Admin Dashboard |
| GET | `/api/v1/ai/core/status` | Admin | - | AIStatusResponse | AI engine status | Admin Dashboard |
| POST | `/api/v1/ai/core/train` | Admin | TrainRequest | TrainResponse | Train AI model | Admin Dashboard |

---

### 5.13 Rating Endpoints

| Method | URL Path | Auth Roles | Request Body | Response | Description | Linked Frontend Page |
|--------|-----------|------------|-------------|----------|-------------|---------------------|
| POST | `/api/v1/ratings` | Patient | RatingCreate | RatingResponse | Submit doctor rating | Post-Consultation |
| GET | `/api/v1/ratings/doctor/{doctor_id}` | Public | - | List[RatingResponse] | Get doctor ratings | Doctor Details |
| GET | `/api/v1/ratings/token/{token_id}` | Patient | - | RatingResponse | Get token rating | Token Details |

---

### 5.14 System Health Endpoints

| Method | URL Path | Auth Roles | Request Body | Response | Description | Linked Frontend Page |
|--------|-----------|------------|-------------|----------|-------------|---------------------|
| GET | `/api/v1/system/health` | Public | - | HealthResponse | System health check | Monitoring |
| GET | `/api/v1/system/status` | Public | - | StatusResponse | System status | Monitoring |
| GET | `/` | Public | - | RootResponse | API root | API Documentation |
| GET | `/ping` | Public | - | PongResponse | Ping endpoint | Monitoring |

---

## 6. Service Layer Map

### 6.1 Core Services

#### QueueManagementService
**File:** `app/services/queue_management_service.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `autoskip_cycle` | - | None | Background Worker | Token, Queue |
| `recalculate_queue_positions_sql` | doctor_id, db | None | Queue endpoints | Token |
| `calculate_patients_ahead` | doctor_id, db | int | Queue status | Token |
| `calculate_queue_length` | doctor_id, db | int | Queue status | Token |
| `calculate_completed_today` | doctor_id, db | int | Dashboard | Token |
| `calculate_queue_velocity` | doctor_id, db | float | AI prediction | Token |
| `get_last_patient_duration` | doctor_id, db | float | Queue estimation | Token |
| `call_next_patient` | doctor_id, hospital_id, db | dict | POST /queue/advance | Token, Queue |
| `_send_queue_update_alerts_for_doctor` | doctor_id, hospital_id, db | None | Queue updates | Token |
| `_send_turn_now_alert` | doctor_id, hospital_id, qdata | None | Consultation | Token |
| `_send_final_alert_for_doctor` | doctor_id, hospital_id | None | Queue updates | Token |

---

#### NotificationService
**File:** `app/services/notification_service.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `send_whatsapp` | phone_number, message | bool | Token creation | - |
| `send_whatsapp_template` | phone_number, template_name, params | bool | Various endpoints | - |
| `send_sms` | phone_number, message | bool | Fallback notifications | - |
| `send_queue_alert` | token_data, queue_data | bool | Queue updates | Token |

---

#### TokenService
**File:** `app/services/token_service.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `generate_token` | doctor_id, hospital_id, patient_id, db | SmartToken | POST /tokens/generate | Token, User, Doctor, Hospital |
| `get_queue_status` | doctor_id, token_number, appointment_date | QueueStatus | Queue endpoints | Token |
| `format_token` | token_number | str | Token display | - |
| `validate_token` | hex_code | bool | Token validation | Token |

---

#### DoctorLeaveService
**File:** `app/services/doctor_leave_service.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `handle_doctor_on_leave` | doctor_id, reason, db | None | Doctor status update | Token, Doctor |
| `notify_affected_patients` | doctor_id, hospital_id, db | None | Leave handling | Token |
| `reschedule_tokens` | doctor_id, suggested_doctor_id, db | None | Leave handling | Token |

---

### 6.2 Scheduling Services

#### ConfirmationScheduler
**File:** `app/services/confirmation_scheduler.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `schedule_confirmation_checks` | token_id, appointment_date | None | Token creation | Token |
| `send_reminder` | token_id | None | APScheduler job | Token |
| `send_final_confirmation` | token_id | None | APScheduler job | Token |

---

#### MessageScheduler
**File:** `app/services/message_scheduler.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `schedule_messages` | token_data, appointment_date | None | Token creation | Token |
| `schedule_reminder` | token_id, delay_minutes | None | APScheduler job | Token |

---

### 6.3 Pharmacy Services

#### PharmacyInventoryService
**File:** `app/services/pharmacy_inventory_service.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `add_medicine` | medicine_data, db | PharmacyMedicine | POST /pharmacy/inventory | PharmacyMedicine |
| `update_stock` | medicine_id, quantity, db | None | PATCH /pharmacy/inventory | PharmacyMedicine |
| `get_low_stock` | hospital_id, threshold | List[PharmacyMedicine] | GET /pharmacy/inventory | PharmacyMedicine |
| `search_medicines` | query, hospital_id | List[PharmacyMedicine] | GET /pharmacy/medicines | PharmacyMedicine |

---

### 6.4 AI Services

#### AIEngine
**File:** `app/services/ai_engine.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `load` | - | None | App startup | - |
| `predict_queue_time` | doctor_id, time_of_day | int | POST /ai/ml/predict | Token (historical) |
| `predict_no_show` | token_data | float | POST /ai/ml/predict | Token (historical) |
| `optimize_doctor_schedule` | doctor_id, date | Schedule | POST /ai/core/train | Token (historical) |

---

### 6.5 Utility Services

#### CacheService
**File:** `app/services/cache_service.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `get` | key | Any | Various endpoints | - |
| `set` | key, value, ttl | None | Various endpoints | - |
| `delete` | key | None | Cache invalidation | - |
| `invalidate_pattern` | pattern | None | Bulk invalidation | - |

---

#### RedisService
**File:** `app/services/redis_service.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `init_redis` | - | None | App startup | - |
| `close_redis` | - | None | App shutdown | - |
| `publish` | channel, message | None | Real-time updates | - |
| `subscribe` | channel | AsyncIterator | WebSocket | - |

---

#### StorageService
**File:** `app/services/storage_service.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `upload_file` | file, filename | str | Profile upload | - |
| `delete_file` | file_url | bool | Profile update | - |
| `get_presigned_url` | filename | str | File download | - |

---

### 6.6 Payment Services

#### RefundService
**File:** `app/services/refund_service.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `process_refund` | token_id, method, reason | Refund | POST /payments/refund | Token, Refund, Wallet |
| `calculate_refund` | token_id | RefundCalculation | Refund request | Token, Payment |
| `credit_wallet` | user_id, amount | None | Wallet refund | Wallet |

---

#### FeeCalculator
**File:** `app/services/fee_calculator.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `calculate_total_fee` | doctor_id, has_session | float | Token creation | Doctor |
| `calculate_session_fee` | doctor_id, sessions | float | Token creation | Doctor |
| `apply_discount` | base_fee, discount_code | float | Payment processing | - |

---

### 6.7 Integration Services

#### SyncService
**File:** `app/services/sync_service.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `sync_pos_to_postgres` | - | None | Background Worker | PharmacyMedicine, PharmacySale |
| `sync_hospital_data` | hospital_id | None | Manual sync | Hospital, Doctor |

---

#### NotificationSchedulerClient
**File:** `app/services/notification_scheduler_client.py`

| Method | Parameters | Return Type | Called By Endpoint | DB Tables |
|--------|------------|-------------|-------------------|-----------|
| `schedule_token_messages` | token_data | None | Token creation | - |
| `send_queue_alert` | token_data, queue_data | None | Queue updates | - |

---

### 6.8 db_automation Services

**File:** `db_automation/services.py`

| Class | Method | Parameters | Return Type | DB Tables |
|-------|--------|------------|-------------|-----------|
| `MedicineService` | `create` | medicine_data | Medicine | pharmacy_medicines |
| `MedicineService` | `get_by_id` | medicine_id | Medicine | pharmacy_medicines |
| `MedicineService` | `list` | filters | List[Medicine] | pharmacy_medicines |
| `MedicineService` | `update` | medicine_id, data | Medicine | pharmacy_medicines |
| `MedicineService` | `delete` | medicine_id | bool | pharmacy_medicines |
| `MedicineService` | `search` | query, hospital_id | List[Medicine] | pharmacy_medicines |
| `InvoiceService` | `create` | invoice_data | Invoice | pharmacy_invoices, pharmacy_invoice_items |
| `InvoiceService` | `get_by_id` | invoice_id | Invoice | pharmacy_invoices, pharmacy_invoice_items |
| `InvoiceService` | `list` | filters | List[Invoice] | pharmacy_invoices |
| `InvoiceService` | `add_item` | invoice_id, item_data | InvoiceItem | pharmacy_invoice_items |
| `SaleService` | `record_sale` | sale_data | Sale | pharmacy_sales |

---

## 7. Authentication & Roles

### 7.1 JWT Flow Diagram

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       │ 1. POST /auth/login
       │    {identifier, password, auth_method}
       │
       ▼
┌─────────────┐
│   FastAPI    │
│   Router     │
└──────┬──────┘
       │
       │ 2. Normalize phone/email
       │
       ▼
┌─────────────┐
│   Auth       │
│   Helper     │
└──────┬──────┘
       │
       │ 3. Query User from PostgreSQL
       │
       ▼
┌─────────────┐
│ PostgreSQL   │
│   User Table │
└──────┬──────┘
       │
       │ 4. Return User object
       │
       ▼
┌─────────────┐
│   Security   │
│   verify_    │
│   password() │
└──────┬──────┘
       │
       │ 5. SHA-256 + bcrypt verify
       │
       ▼
┌─────────────┐
│   Security   │
│   create_    │
│   access_    │
│   token()    │
└──────┬──────┘
       │
       │ 6. Generate JWT
       │    {sub: user_id, role: role, hospital_id: hospital_id}
       │
       ▼
┌─────────────┐
│   Response   │
│   {access_   │
│    token,    │
│    refresh_  │
│    token}    │
└──────┬──────┘
       │
       │ 7. Return to client
       │
       ▼
┌─────────────┐
│   Client     │
│   Store JWT  │
└─────────────┘

┌─────────────┐
│   Client     │
│   Protected │
│   Request    │
└──────┬──────┘
       │
       │ 8. Request with Authorization: Bearer <token>
       │
       ▼
┌─────────────┐
│   FastAPI    │
│   OAuth2     │
│   Scheme     │
└──────┬──────┘
       │
       │ 9. Extract token
       │
       ▼
┌─────────────┐
│   Security   │
│   verify_    │
│   token()    │
└──────┬──────┘
       │
       │ 10. Decode JWT
       │
       ▼
┌─────────────┐
│   Security   │
│   get_       │
│   current_   │
│   user()     │
└──────┬──────┘
       │
       │ 11. Query User from PostgreSQL
       │
       ▼
┌─────────────┐
│ PostgreSQL   │
│   User Table │
└──────┬──────┘
       │
       │ 12. Return TokenData
       │
       ▼
┌─────────────┐
│   Endpoint   │
│   Handler    │
└─────────────┘
```

### 7.2 Role Definitions

| Role | Description | Permissions |
|------|-------------|-------------|
| **PATIENT** | End users who book appointments | - Book tokens<br>- View own tokens<br>- Cancel own tokens<br>- Update profile<br>- Submit ratings<br>- Make payments |
| **DOCTOR** | Healthcare providers | - View/manage own queue<br>- Start/end consultations<br>- Update availability<br>- View patient tokens<br>- Set leave status<br>- View ratings |
| **RECEPTIONIST** | Hospital staff | - Manage hospital tokens<br>- Create/manage doctors<br>- View hospital queue<br>- Handle walk-ins<br>- Manage appointments |
| **ADMIN** | System administrators | - Full system access<br>- Manage hospitals<br>- Manage all users<br>- System configuration<br>- View analytics<br>- Manage POS sync |
| **PHARMACY** | Pharmacy staff | - Manage inventory<br>- Create invoices<br>- Process sales<br>- View prescriptions<br>- Manage stock |

### 7.3 Role-Based Access Control

**Decorator:** `@require_roles(*allowed_roles)`

**Usage Example:**
```python
@router.post("/staff/doctors/")
@require_roles("admin", "receptionist")
async def create_doctor(...):
    # Only admin and receptionist can access
```

**Portal Access:** `@require_portal_user()` allows all portal roles (patient, doctor, admin, pharmacist, pharmacy)

### 7.4 Endpoint Access Matrix

| Endpoint Pattern | PATIENT | DOCTOR | RECEPTIONIST | ADMIN | PHARMACY |
|-----------------|---------|--------|-------------|-------|----------|
| `/api/v1/auth/*` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `/api/v1/public/*` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `/api/v1/patient/*` | ✅ | ❌ | ❌ | ✅ | ❌ |
| `/api/v1/staff/*` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `/api/v1/staff/pharmacy/*` | ❌ | ❌ | ❌ | ✅ | ✅ |
| `/api/v1/ai/*` | ❌ | ❌ | ❌ | ✅ | ❌ |
| `/api/v1/external/*` | ❌ | ❌ | ❌ | ✅ | ❌ |

---

## 8. Page to API Linkage

### 8.1 Patient App Pages

| Page | API Endpoints Called |
|------|---------------------|
| **Login/Signup** | POST `/api/v1/auth/register`, POST `/api/v1/auth/login`, GET `/api/v1/auth/check-phone/{phone}` |
| **OTP Login** | POST `/api/v1/auth/otp/send`, POST `/api/v1/auth/otp/verify` |
| **Patient Dashboard** | GET `/api/v1/patient/dashboard`, GET `/api/v1/patient/actions/activities` |
| **Profile** | GET `/api/v1/patient/profile`, PATCH `/api/v1/patient/profile` |
| **Hospital Search** | GET `/api/v1/public/hospitals/search`, GET `/api/v1/public/hospitals/nearby`, GET `/api/v1/public/hospitals/open` |
| **Hospital Details** | GET `/api/v1/public/hospitals/{hospital_id}`, GET `/api/v1/public/hospitals/{hospital_id}/doctors`, GET `/api/v1/public/hospitals/{hospital_id}/categories` |
| **Doctor Search** | GET `/api/v1/public/doctors/`, GET `/api/v1/public/doctors/category/{category}` |
| **Doctor Details** | GET `/api/v1/public/doctors/{doctor_id}`, GET `/api/v1/patient/queue/doctor/{doctor_id}` |
| **Book Appointment** | POST `/api/v1/patient/tokens/generate`, POST `/api/v1/patient/tokens/generate/details` |
| **My Tokens** | GET `/api/v1/patient/tokens/`, GET `/api/v1/patient/tokens/{token_id}` |
| **Token Details** | GET `/api/v1/patient/tokens/{token_id}`, GET `/api/v1/patient/queue/position/{token_id}`, GET `/api/v1/patient/payments/token/{token_id}` |
| **Cancel Token** | DELETE `/api/v1/patient/tokens/{token_id}/cancel`, POST `/api/v1/patient/tokens/{token_id}/cancel` |
| **Payment** | POST `/api/v1/patient/payments/create`, GET `/api/v1/patient/payments/{payment_id}` |
| **Payment History** | GET `/api/v1/patient/payments/token/{token_id}` |
| **Rate Doctor** | POST `/api/v1/ratings`, GET `/api/v1/ratings/token/{token_id}` |
| **Settings** | POST `/api/v1/patient/actions/location` |

---

### 8.2 Doctor Portal Pages

| Page | API Endpoints Called |
|------|---------------------|
| **Doctor Dashboard** | GET `/api/v1/staff/portal/notifications`, GET `/api/v1/staff/realtime/queue/{doctor_id}` |
| **Queue Management** | GET `/api/v1/patient/queue/doctor/{doctor_id}`, POST `/api/v1/patient/queue/advance`, POST `/api/v1/patient/queue/pause`, POST `/api/v1/patient/queue/resume` |
| **Consultation** | POST `/api/v1/staff/consultation/start`, POST `/api/v1/staff/consultation/end` |
| **Availability** | PATCH `/api/v1/staff/doctors/{doctor_id}/status`, GET `/api/v1/staff/doctors/{doctor_id}/availability` |
| **Patient Tokens** | GET `/api/v1/staff/portal/tokens/active` |
| **Ratings** | GET `/api/v1/ratings/doctor/{doctor_id}` |
| **Leave Management** | PATCH `/api/v1/staff/doctors/{doctor_id}/status` (with on_leave) |

---

### 8.3 Reception Portal Pages

| Page | API Endpoints Called |
|------|---------------------|
| **Reception Dashboard** | GET `/api/v1/staff/portal/notifications`, GET `/api/v1/staff/portal/tokens/active` |
| **Hospital Management** | POST `/api/v1/public/hospitals/`, PATCH `/api/v1/public/hospitals/{hospital_id}` |
| **Doctor Management** | POST `/api/v1/staff/doctors/`, PATCH `/api/v1/staff/doctors/{doctor_id}`, GET `/api/v1/staff/doctors/{doctor_id}` |
| **Token Management** | GET `/api/v1/patient/tokens/list/hospital/{hospital_id}`, POST `/api/v1/patient/tokens/generate` (walk-in) |
| **Queue Overview** | GET `/api/v1/patient/queue/doctor/{doctor_id}` (for all doctors) |
| **Patient Check-in** | POST `/api/v1/patient/tokens/generate/details` |

---

### 8.4 Admin Dashboard Pages

| Page | API Endpoints Called |
|------|---------------------|
| **Admin Dashboard** | GET `/api/v1/patient/dashboard`, GET `/api/v1/system/health` |
| **Hospital Management** | GET `/api/v1/public/hospitals/`, POST `/api/v1/public/hospitals/`, DELETE `/api/v1/staff/doctors/{hospital_id}` |
| **User Management** | GET `/api/v1/patient/profile` (for any user), PATCH `/api/v1/patient/profile` |
| **System Health** | GET `/api/v1/system/health`, GET `/api/v1/system/status` |
| **AI/ML** | POST `/api/v1/ai/ml/predict`, GET `/api/v1/ai/core/status`, POST `/api/v1/ai/core/train` |
| **POS Sync** | GET `/api/v1/external/pos/sync` |
| **Analytics** | Custom endpoints for reporting |

---

### 8.5 Pharmacy Portal Pages

| Page | API Endpoints Called |
|------|---------------------|
| **Pharmacy Dashboard** | GET `/api/v1/staff/portal/notifications` |
| **Inventory** | GET `/api/v1/staff/pharmacy/inventory`, POST `/api/v1/staff/pharmacy/inventory`, PATCH `/api/v1/staff/pharmacy/inventory/{id}`, DELETE `/api/v1/staff/pharmacy/inventory/{id}` |
| **Medicine Search** | GET `/api/v1/public/pharmacy/medicines` |
| **Invoicing** | POST `/api/v1/staff/pharmacy/invoices`, GET `/api/v1/staff/pharmacy/invoices`, GET `/api/v1/staff/pharmacy/invoices/{invoice_id}` |
| **Sales** | POST `/api/v1/staff/pharmacy/invoices` (with sale items) |

---

## 9. Background Services

### 9.1 APScheduler Jobs

| Job Name | Schedule | Trigger | Purpose | API Endpoints Affected |
|-----------|----------|---------|---------|----------------------|
| **Auto-skip Worker** | Every 60s (configurable) | AsyncIO Task | Automatically skip patients who don't show up after grace period | Queue status, Token status |
| **POS Sync Worker** | Every 5 minutes | AsyncIO Task | Sync pharmacy data from external POS system to PostgreSQL | Pharmacy inventory |
| **Confirmation Reminder** | Scheduled per token | Date Trigger | Send reminder WhatsApp message before appointment | Token confirmation |
| **Final Confirmation Check** | Scheduled per token | Date Trigger | Send final confirmation request | Token confirmation |
| **Queue Update Alert** | Dynamic per queue | Interval Trigger | Send queue position updates to patients | Queue status |

---

### 9.2 Async Background Tasks

| Task | Trigger | Function | Purpose |
|------|---------|----------|---------|
| **QueueManagementService.autoskip_cycle** | App startup (asyncio.create_task) | Runs in infinite loop | Scan for called tokens past grace period and mark as skipped |
| **sync_pos_to_postgres** | App startup (asyncio.create_task) | Runs in infinite loop | Sync pharmacy medicines from POS to PostgreSQL |
| **WhatsApp Template Sending** | Token creation, queue updates | async HTTP call | Send WhatsApp messages via Twilio |
| **AI Model Loading** | App startup | ai_engine.load() | Load XGBoost model for predictions |

---

### 9.3 Startup Sequence

```
1. FastAPI lifespan() starts
2. Initialize Firebase (legacy)
3. Start Auto-skip worker (asyncio.create_task)
4. Start POS sync worker (asyncio.create_task)
5. Start APScheduler
6. Load AI Engine model
7. Initialize Redis/Upstash
8. App is ready to serve requests
```

---

### 9.4 Shutdown Sequence

```
1. FastAPI lifespan() cleanup
2. Cancel Auto-skip task
3. Cancel POS sync task
4. Shutdown APScheduler
5. Close Redis connection
6. App shutdown complete
```

---

## 10. Third Party Integrations

### 10.1 WhatsApp API (Twilio)

**Purpose:** Send appointment notifications, queue updates, and confirmation messages to patients via WhatsApp.

**Templates Used:**
| Template Name | Template SID | Trigger | Parameters |
|---------------|--------------|---------|-------------|
| `token_number` | TWILIO_TOKEN_NUMBER_SID | Token creation | patient_name, token_number, doctor_name, appointment_time |
| `reminder_for_confirmation` | TWILIO_REMINDER_CONFIRM_SID | Scheduled reminder | patient_name, doctor_name, appointment_time |
| `queue_update` | TWILIO_QUEUE_UPDATE_SID | Queue position change | patient_name, patients_ahead, wait_time, department, token_number |
| `patient_call_alert` | TWILIO_CALL_ALERT_SID | Patient called | patient_name, doctor_name, consultation_room |
| `final_alert` | TWILIO_FINAL_ALERT_SID | 2nd in queue | patient_name, doctor_name, estimated_time |
| `appointment_doctor_change` | TWILIO_DOCTOR_CHANGE_SID | Doctor leave/reschedule | patient_name, old_doctor, new_doctor, new_time |
| `cancelled` | TWILIO_CANCELLED_SID | Token cancellation | patient_name, doctor_name, refund_amount |
| `skipped` | TWILIO_SKIPPED_SID | Token skipped | patient_name, doctor_name, new_token_number |
| `template` (Thankyou) | TWILIO_THANKYOU_SID | Consultation complete | (no parameters) |
| `otp` | TWILIO_OTP_SID | OTP login | otp_code |

**Service File:** `app/services/whatsapp_service.py`

**Key Methods:**
- `send_template_message(phone_number, template_name, parameters)`
- `send_text_message(phone_number, message)`

**Webhook:** `/api/v1/webhooks/whatsapp` handles incoming WhatsApp messages (YES/CANCEL replies)

---

### 10.2 Firebase Firestore (Legacy)

**Purpose:** Original database system being migrated to PostgreSQL.

**Status:** Migration in progress. Most core tables migrated to PostgreSQL. Firebase still used for:
- Some legacy collections
- Real-time listeners (being replaced by WebSocket/Redis)

**Collections:** Defined in `app/config.py` COLLECTIONS dictionary

**Migration Guide:** See `COMPLETE_MIGRATION_GUIDE.md`

---

### 10.3 Redis/Upstash

**Purpose:** Caching and Pub/Sub for real-time WebSocket broadcasting across multiple instances.

**Configuration:**
- `REDIS_URL` environment variable
- Used for distributed WebSocket message broadcasting
- Cache layer for frequently accessed data

**Service File:** `app/services/redis_service.py`

**Key Methods:**
- `init_redis()` - Initialize connection
- `close_redis()` - Close connection
- `publish(channel, message)` - Publish to channel
- `subscribe(channel)` - Subscribe to channel

**Use Cases:**
- Real-time queue updates across multiple server instances
- Session caching
- Rate limiting

---

### 10.4 AI/ML Engine (XGBoost)

**Purpose:** Predict queue wait times and patient no-show probability.

**Model:** XGBoost regression model

**Service File:** `app/services/ai_engine.py`

**Key Methods:**
- `load()` - Load trained model
- `predict_queue_time(doctor_id, time_of_day)` - Predict wait time in minutes
- `predict_no_show(token_data)` - Predict probability of no-show
- `optimize_doctor_schedule(doctor_id, date)` - Optimize schedule

**Training Data:** Historical token data from PostgreSQL

**API Endpoints:**
- `POST /api/v1/ai/ml/predict` - Get predictions
- `POST /api/v1/ai/core/train` - Retrain model
- `GET /api/v1/ai/core/status` - Model status

---

### 10.5 OpenStreetMap (OSM)

**Purpose:** Geolocation services for hospital search and nearby hospitals.

**APIs Used:**
- **Overpass API:** Query nearby hospitals by coordinates
- **Nominatim API:** Search hospitals by location name

**Endpoints:**
- `GET /api/v1/public/hospitals/nearby-overpass` - Overpass API
- `GET /api/v1/public/hospitals/nearby-osm` - Nominatim API

**Service:** Integrated directly in hospital routes

---

### 10.6 POS System Integration

**Purpose:** Sync pharmacy inventory and sales data from external POS system.

**Configuration:**
- `POS_SYSTEM_BASE_URL` - POS system API base URL
- `POS_SYSTEM_API_KEY` - API authentication key
- `POS_WEBHOOK_SECRET` - Webhook secret

**Endpoints:**
- `POST /api/v1/external/pos/webhook` - Receive POS webhooks
- `GET /api/v1/external/pos/sync` - Manual sync trigger

**Service File:** `app/services/sync_service.py`

**Sync Interval:** Every 5 minutes (background worker)

---

### 10.7 Cloudflare R2 / S3 Storage

**Purpose:** Store user avatars and medical records.

**Configuration:**
- `AWS_ACCESS_KEY_ID` - Access key
- `AWS_SECRET_ACCESS_KEY` - Secret key
- `R2_ENDPOINT_URL` - R2 endpoint
- `R2_BUCKET_NAME` - Bucket name
- `R2_REGION` - Region

**Service File:** `app/services/storage_service.py`

**Key Methods:**
- `upload_file(file, filename)` - Upload file
- `delete_file(file_url)` - Delete file
- `get_presigned_url(filename)` - Get download URL

---

## 11. Error Handling

### 11.1 Global Exception Handlers

**Location:** `main.py`

| Exception Type | Handler | Status Code | Error Code | Response Format |
|----------------|---------|-------------|------------|-----------------|
| `Exception` | `global_exception_handler` | 500 | INTERNAL_SERVER_ERROR | Standard fail response |
| `PulseQException` | `pulseq_exception_handler` | Variable | From exception | Standard fail response with error_code |
| `HTTPException` | `http_exception_handler` | From exception | Mapped from status | Standard fail response |
| `RequestValidationError` | `validation_exception_handler` | 422 | VALIDATION_ERROR | Standard fail with errors detail |
| `404 Not Found` | `not_found_handler` | 404 | NOT_FOUND | Standard fail response |

---

### 11.2 Standard Response Format

**Success Response:**
```python
{
    "success": true,
    "data": { ... },
    "message": "Operation successful"
}
```

**Error Response:**
```python
{
    "success": false,
    "error_code": "ERROR_CODE",
    "message": "Error description",
    "data": { ... }  # Optional additional error details
}
```

**Helper Functions:** `app/utils/responses.py`
- `ok(data, message)` - Success response
- `fail(message, error_code, status_code, data)` - Error response

---

### 11.3 Custom Exceptions

**File:** `app/exceptions.py`

| Exception | Error Code | Description |
|------------|------------|-------------|
| `PulseQException` | Variable | Base exception with error_code support |
| `TokenNotFoundException` | TOKEN_NOT_FOUND | Token not found |
| `InvalidTokenTransition` | INVALID_TOKEN_STATE | Invalid token status transition |
| `DoctorUnavailableException` | DOCTOR_UNAVAILABLE | Doctor not available |
| `PaymentFailedException` | PAYMENT_FAILED | Payment processing failed |
| `RefundException` | REFUND_FAILED | Refund processing failed |

---

### 11.4 Validation Errors

**Pydantic Validation:**
- Automatic validation of request bodies
- Field-level validators in Pydantic models
- Custom validators in `app/models.py`

**Common Validation Errors:**
- Phone number format
- Email format
- Password strength
- Enum value validation
- Date/time format

---

## 12. Deployment

### 12.1 Server Setup

**Requirements:**
- Python 3.9+
- PostgreSQL 13+
- Redis (Upstash recommended)
- Node.js (for notification service, optional)

**Recommended Server:**
- DigitalOcean App Platform or Render
- Minimum 2GB RAM, 2 vCPUs
- SSD storage for database

---

### 12.2 Environment Variables

**Required Variables:**

```bash
# Application
PROJECT_NAME=PulseQBackend
DEBUG=False
HOST=0.0.0.0
PORT=8000

# Database
DATABASE_URL=postgresql://user:password@host:port/dbname

# JWT
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_DAYS=7

# Firebase (Legacy)
FIREBASE_SERVICE_ACCOUNT_KEY=path/to/service-account.json

# Twilio WhatsApp
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
TWILIO_TOKEN_NUMBER_SID=your-template-sid
TWILIO_CALL_ALERT_SID=your-template-sid
TWILIO_FINAL_ALERT_SID=your-template-sid
TWILIO_DOCTOR_CHANGE_SID=your-template-sid
TWILIO_CANCELLED_SID=your-template-sid
TWILIO_THANKYOU_SID=your-template-sid
TWILIO_SKIPPED_SID=your-template-sid
TWILIO_REMINDER_CONFIRM_SID=your-template-sid
TWILIO_QUEUE_UPDATE_SID=your-template-sid
TWILIO_OTP_SID=your-template-sid

# Redis/Upstash
REDIS_URL=redis://default:password@host:port

# Cloudflare R2
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
R2_ENDPOINT_URL=https://your-account.r2.cloudflarestorage.com
R2_BUCKET_NAME=your-bucket-name
R2_REGION=us-east-1

# POS System
POS_SYSTEM_BASE_URL=http://localhost:5000
POS_SYSTEM_API_KEY=your-api-key
POS_WEBHOOK_SECRET=your-webhook-secret

# Queue Configuration
AVG_CONSULTATION_TIME_MINUTES=5
QUEUE_GRACE_TIME_MINUTES=3
QUEUE_SMART_NOTIFY_POSITION_THRESHOLD=4
QUEUE_SMART_NOTIFY_WAIT_THRESHOLD_MINUTES=15
QUEUE_AUTOSKIP_INTERVAL_SECONDS=60

# CORS
ALLOWED_ORIGINS=https://patient.pulseq.health,https://pharmacy.pulseq.health,https://admin.pulseq.health,https://reception.pulseq.health,https://doctor.pulseq.health
TRUSTED_HOSTS=pulseq.health
```

---

### 12.3 How to Run

**Local Development:**

```bash
# 1. Clone repository
git clone <repo-url>
cd PulseQ_Backend/backend

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.template .env
# Edit .env with your values

# 5. Run database migrations
alembic upgrade head

# 6. Start the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Production Deployment:**

```bash
# Using Gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Using Docker
docker build -t pulseq-backend .
docker run -p 8000:8000 --env-file .env pulseq-backend

# Using Render/DigitalOcean
# Connect repository
# Set environment variables in dashboard
# Deploy automatically on push
```

---

### 12.4 Database Migrations

**Create Migration:**
```bash
alembic revision --autogenerate -m "description"
```

**Apply Migration:**
```bash
alembic upgrade head
```

**Rollback Migration:**
```bash
alembic downgrade -1
```

---

### 12.5 Monitoring

**Health Check:**
```bash
curl https://your-api.com/ping
```

**Performance Monitoring:**
- Response times logged by PerformanceMiddleware
- Slow endpoint warnings (>300ms)
- Very slow endpoint errors (>1000ms)

**Logging:**
- Structured logging via `app/logger.py`
- Log levels: DEBUG, INFO, WARNING, ERROR
- Log to stdout (container-friendly)

---

### 12.6 Scaling Considerations

**Horizontal Scaling:**
- Use Redis/Upstash for distributed WebSocket broadcasting
- Use PostgreSQL connection pooling
- Deploy multiple instances behind load balancer

**Vertical Scaling:**
- Increase RAM for larger datasets
- More CPU for AI/ML predictions
- SSD storage for database I/O

**Caching Strategy:**
- Redis for session data
- In-memory cache for frequently accessed data
- CDN for static assets

---

## Appendix

### A. API Documentation

- **Swagger UI:** `https://your-api.com/docs`
- **ReDoc:** `https://your-api.com/redoc`
- **OpenAPI Spec:** `https://your-api.com/openapi.json`

### B. Support

- **GitHub Issues:** [Repository Issues]
- **Documentation:** [Wiki/Docs]
- **Email:** support@pulseq.health

### C. Changelog

See `CHANGELOG.md` for version history and updates.

---

**Document End**

*This document is maintained by the PulseQ development team. Last updated: May 24, 2026*

---
description: Repository Information Overview
alwaysApply: true
---

# PharmaLabs Information

## Summary
PharmaLabs is a collaborative platform dedicated to the management, extraction, annotation, and review of regulatory documents (PDF). It serves different user roles (Metadonneur, Annotateur, Expert, Client) with specific functionalities optimized for the entire document lifecycle.

## Structure
- **rawdocs**: Core app for document management, annotation, and processing
- **expert**: Expert review interface for validating annotations
- **client**: Client-facing interfaces (library, products, reports, submissions)
- **chatbot**: AI assistant functionality
- **templates**: HTML templates organized by app/role
- **static**: CSS, JavaScript, and other static assets
- **media**: Uploaded documents stored in timestamped directories
- **MyProject**: Main Django project configuration

## Language & Runtime
**Language**: Python 3.10/3.12
**Version**: Django 5.2.3
**Build System**: Django ORM with SQLite
**Package Manager**: pip

## Dependencies
**Main Dependencies**:
- Django 5.2.3
- Django REST Framework 3.16.0
- spaCy 3.8.7 with English and French models
- PyPDF2 3.0.1 and pdfplumber for PDF processing
- pymongo for MongoDB integration
- reportlab 4.4.2 for PDF generation
- pandas for data analysis
- PyMuPDF for PDF manipulation

**Development Dependencies**:
- rich 14.0.0 for improved console output
- pytest for testing

## Build & Installation
```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start development server
python manage.py runserver
```

## Database
**Primary**: SQLite (db.sqlite3)
**Secondary**: MongoDB for annotation storage
**Models**: Document-centric with RawDocument, DocumentPage, Annotation, AnnotationType

## Main Features
- **Document Upload & Processing**: PDF upload with automatic metadata extraction
- **Annotation System**: Manual and AI-assisted annotation of regulatory documents
- **Expert Review**: Validation workflow for annotations with JSON generation
- **Client Interface**: Library, Products, Submissions, and Reports sections
- **Reporting**: KPI dashboards and analytics for regulatory documents

## Key Files
- **manage.py**: Django management script
- **MyProject/settings.py**: Main configuration
- **rawdocs/models.py**: Core data models
- **rawdocs/views.py**: Document processing logic
- **expert/views.py**: Expert review functionality
- **templates/**: UI templates for different user roles

## Issues Identified
- **Synchronization Issue**: The expert module has a synchronization problem between annotation summaries and JSON data
- **Save Message**: The save confirmation message doesn't show which entities were changed
- **Document Synchronization**: The synchronization between summary and JSON doesn't work properly

## Authentication
- Role-based access control with Django groups
- Custom user profiles with role-specific permissions
- Login redirects to role-appropriate dashboards

## Deployment
- Configured for deployment on Render.com
- Environment variables loaded from .env file
- Static files served via Django
- Media files stored in local filesystem
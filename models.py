from app import db
from datetime import datetime
from sqlalchemy import Index

class ReflixTracking(db.Model):
    __tablename__ = 'reflix_tracking'
    
    id = db.Column(db.Integer, primary_key=True)
    reference_number = db.Column(db.String(11), nullable=False, index=True)
    shipping_unit_ref = db.Column(db.String(20), nullable=True)
    status = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200), nullable=True)
    log_file_name = db.Column(db.String(255), nullable=False)
    log_timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Create composite index for efficient queries and unique constraint for idempotency
    __table_args__ = (
        Index('idx_ref_timestamp', 'reference_number', 'timestamp'),
        Index('idx_ref_status', 'reference_number', 'status'),
        Index('idx_unique_tracking', 'reference_number', 'status', 'timestamp', 'log_file_name', unique=True),
    )
    
    def __repr__(self):
        return f'<ReflixTracking {self.reference_number}: {self.status}>'

class LogFile(db.Model):
    __tablename__ = 'log_files'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False, unique=True)
    file_size = db.Column(db.Integer, nullable=False)
    upload_timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    processed = db.Column(db.Boolean, nullable=False, default=False)
    records_extracted = db.Column(db.Integer, nullable=False, default=0)
    error_message = db.Column(db.Text, nullable=True)
    
    def __repr__(self):
        return f'<LogFile {self.filename}>'

class MonitoredFolder(db.Model):
    __tablename__ = 'monitored_folders'
    
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(500), nullable=False, unique=True)
    include_patterns = db.Column(db.String(255), nullable=False, default='*.txt,*.log')
    exclude_patterns = db.Column(db.String(255), nullable=True)
    polling_interval = db.Column(db.Integer, nullable=False, default=10)  # seconds
    max_files = db.Column(db.Integer, nullable=False, default=10)
    active = db.Column(db.Boolean, nullable=False, default=True)
    last_run_at = db.Column(db.DateTime, nullable=True)
    
    # New fields for enhanced functionality
    access_mode = db.Column(db.String(20), nullable=False, default='safe')  # safe, home_desktop, unrestricted
    rotation_base = db.Column(db.String(255), nullable=True)  # e.g., 'log_tracktrace.log'
    rotation_max = db.Column(db.Integer, nullable=False, default=10)  # max .1, .2, ..., .N files
    schedule_enabled = db.Column(db.Boolean, nullable=False, default=False)  # scheduled vs continuous
    schedule_every_minutes = db.Column(db.Integer, nullable=False, default=120)  # 2 hours default
    
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to file states
    file_states = db.relationship('MonitoredFileState', backref='folder', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<MonitoredFolder {self.path}>'

class MonitoredFileState(db.Model):
    __tablename__ = 'monitored_file_states'
    
    id = db.Column(db.Integer, primary_key=True)
    folder_id = db.Column(db.Integer, db.ForeignKey('monitored_folders.id'), nullable=False)
    path = db.Column(db.String(500), nullable=False)
    inode = db.Column(db.BigInteger, nullable=True)
    last_size = db.Column(db.BigInteger, nullable=False, default=0)
    last_mtime = db.Column(db.DateTime, nullable=True)
    last_offset = db.Column(db.BigInteger, nullable=False, default=0)
    generation = db.Column(db.Integer, nullable=False, default=1)
    last_seen = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_error = db.Column(db.Text, nullable=True)
    records_processed = db.Column(db.Integer, nullable=False, default=0)
    
    # Create unique constraint on folder_id + path
    __table_args__ = (
        Index('idx_folder_path', 'folder_id', 'path', unique=True),
    )
    
    def __repr__(self):
        return f'<MonitoredFileState {self.path}>'

class MonitorInstance(db.Model):
    __tablename__ = 'monitor_instance'
    
    id = db.Column(db.String(50), primary_key=True)  # singleton row with id='monitor'
    active = db.Column(db.Boolean, nullable=False, default=False)
    stop_requested = db.Column(db.Boolean, nullable=False, default=False)
    process_id = db.Column(db.Integer, nullable=True)
    worker_id = db.Column(db.String(100), nullable=True)
    heartbeat_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    stopped_at = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<MonitorInstance {self.id}: active={self.active}, process_id={self.process_id}>'

import os
import time
import glob
import threading
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from app import app, db
from models import MonitoredFolder, MonitoredFileState, MonitorInstance
from tail_parser import TailParser

logger = logging.getLogger(__name__)

class FolderMonitor:
    """
    Background service that monitors folders for REFLIV log files,
    processes them incrementally, and maintains a maximum file count.
    """
    
    def __init__(self):
        self.is_running = False
        self.monitor_thread = None
        self.tail_parsers = {}  # Dictionary of file_path -> TailParser instances
        self.instance_id = "monitor"
        self.process_id = os.getpid()
        self.worker_id = f"worker-{self.process_id}-{int(time.time())}"
        
    def start(self):
        """Start the folder monitoring service."""
        if self.is_running:
            logger.warning("Monitor is already running")
            return False
            
        # Try to acquire singleton lock
        if not self._acquire_singleton_lock():
            logger.warning("Another monitor instance is already running")
            return False
            
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Folder monitor started successfully")
        return True
    
    def stop(self):
        """Stop the folder monitoring service."""
        if not self.is_running:
            logger.info("Monitor is already stopped")
            return
        
        logger.info(f"Stopping monitor (PID: {self.process_id}, Worker: {self.worker_id})")
        self.is_running = False
        
        # Signal stop via database for cross-worker communication
        self._signal_stop_via_database()
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=10)  # Increased timeout
            
        self._release_singleton_lock()
        logger.info("Folder monitor stopped successfully")
    
    def _signal_stop_via_database(self):
        """Signal stop request via database for cross-worker communication."""
        try:
            with app.app_context():
                instance = db.session.query(MonitorInstance).filter_by(
                    id=self.instance_id
                ).with_for_update().first()
                
                if instance:
                    instance.stop_requested = True
                    instance.heartbeat_at = datetime.utcnow()
                    db.session.commit()
                    logger.info("Stop signal sent via database")
                else:
                    logger.warning("No monitor instance found to signal stop")
                    
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to signal stop via database: {e}")
    
    def _acquire_singleton_lock(self) -> bool:
        """Acquire singleton lock atomically using SELECT FOR UPDATE."""
        try:
            with app.app_context():
                # Begin transaction and acquire row-level lock
                instance = db.session.query(MonitorInstance).filter_by(
                    id=self.instance_id
                ).with_for_update().first()
                
                current_time = datetime.utcnow()
                
                if instance:
                    # Check if it's stale (no heartbeat in last 60 seconds)
                    if instance.active and instance.heartbeat_at:
                        time_since_heartbeat = current_time - instance.heartbeat_at
                        if time_since_heartbeat < timedelta(seconds=60):
                            db.session.rollback()
                            logger.info(f"Active monitor instance exists (PID: {instance.process_id}, Worker: {instance.worker_id})")
                            return False  # Active instance exists
                    
                    # Update existing instance atomically
                    instance.active = True
                    instance.stop_requested = False
                    instance.process_id = self.process_id
                    instance.worker_id = self.worker_id
                    instance.heartbeat_at = current_time
                    instance.started_at = current_time
                    instance.stopped_at = None
                else:
                    # Create new instance atomically
                    instance = MonitorInstance()
                    instance.id = self.instance_id
                    instance.active = True
                    instance.stop_requested = False
                    instance.process_id = self.process_id
                    instance.worker_id = self.worker_id
                    instance.heartbeat_at = current_time
                    instance.started_at = current_time
                    db.session.add(instance)
                
                db.session.commit()
                logger.info(f"Singleton lock acquired successfully (PID: {self.process_id}, Worker: {self.worker_id})")
                return True
                
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to acquire singleton lock: {e}")
            return False
    
    def _release_singleton_lock(self):
        """Release singleton lock with proper transaction handling."""
        try:
            with app.app_context():
                # Use SELECT FOR UPDATE for atomic release
                instance = db.session.query(MonitorInstance).filter_by(
                    id=self.instance_id
                ).with_for_update().first()
                
                if instance:
                    instance.active = False
                    instance.stop_requested = False
                    instance.heartbeat_at = datetime.utcnow()
                    instance.stopped_at = datetime.utcnow()
                    db.session.commit()
                    logger.info(f"Singleton lock released successfully (PID: {self.process_id}, Worker: {self.worker_id})")
                else:
                    logger.warning("No monitor instance found to release")
                    
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to release singleton lock: {e}")
    
    def _update_heartbeat(self) -> bool:
        """Update heartbeat and check for stop signal. Returns True if should continue running."""
        try:
            with app.app_context():
                instance = db.session.query(MonitorInstance).filter_by(
                    id=self.instance_id
                ).with_for_update().first()
                
                if instance:
                    # Check for stop request from other workers
                    if instance.stop_requested:
                        logger.info(f"Stop signal received from database (PID: {instance.process_id}, Worker: {instance.worker_id})")
                        return False
                    
                    # Update heartbeat
                    instance.heartbeat_at = datetime.utcnow()
                    db.session.commit()
                    return True
                else:
                    logger.error("Monitor instance not found during heartbeat update")
                    return False
                    
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update heartbeat: {e}")
            return False
    
    def _monitor_loop(self):
        """Main monitoring loop with cross-worker stop signal checking."""
        with app.app_context():
            logger.info(f"Monitor loop started (PID: {self.process_id}, Worker: {self.worker_id})")
            
            while self.is_running:
                try:
                    # Update heartbeat and check for stop signal from database
                    if not self._update_heartbeat():
                        logger.info("Monitor loop stopping due to database stop signal")
                        self.is_running = False
                        break
                    
                    # Get active monitored folders
                    folders = MonitoredFolder.query.filter_by(active=True).all()
                    
                    for folder in folders:
                        # Check stop conditions before processing each folder
                        if not self.is_running:
                            break
                        
                        # Quick stop signal check during folder processing
                        try:
                            instance = MonitorInstance.query.filter_by(id=self.instance_id).first()
                            if instance and instance.stop_requested:
                                logger.info("Stop signal detected during folder processing")
                                self.is_running = False
                                break
                        except Exception as e:
                            logger.warning(f"Error checking stop signal: {e}")
                            
                        # Check if folder should be processed (scheduled vs continuous)
                        should_process = True
                        if folder.schedule_enabled:
                            if folder.last_run_at:
                                next_run = folder.last_run_at + timedelta(minutes=folder.schedule_every_minutes)
                                should_process = datetime.utcnow() >= next_run
                            # If last_run_at is None, process immediately
                        
                        if should_process:
                            self._process_folder(folder)
                            
                            # Update folder's last run time
                            folder.last_run_at = datetime.utcnow()
                            db.session.commit()
                        else:
                            # Log next scheduled run time
                            next_run = folder.last_run_at + timedelta(minutes=folder.schedule_every_minutes)
                            time_until_next = (next_run - datetime.utcnow()).total_seconds()
                            logger.debug(f"Folder {folder.path} scheduled in {time_until_next/60:.1f} minutes")
                    
                    # Sleep for polling interval (use minimum from all folders, default 10s)
                    if folders:
                        min_interval = min(folder.polling_interval for folder in folders)
                        sleep_time = max(min_interval, 1)  # At least 1 second
                    else:
                        sleep_time = 10  # Default 10 seconds if no folders configured
                    
                    # Sleep in smaller chunks to respond faster to stop signals
                    for _ in range(sleep_time):
                        if not self.is_running:
                            break
                        time.sleep(1)
                        
                except Exception as e:
                    logger.error(f"Error in monitor loop: {e}")
                    # Sleep in smaller chunks even during error recovery
                    for _ in range(10):
                        if not self.is_running:
                            break
                        time.sleep(1)
                        
            logger.info(f"Monitor loop ended (PID: {self.process_id}, Worker: {self.worker_id})")
    
    def _process_folder(self, folder: MonitoredFolder):
        """Process a single monitored folder."""
        try:
            if not os.path.exists(folder.path):
                logger.warning(f"Monitored folder does not exist: {folder.path}")
                return
            
            # Get current files matching patterns
            current_files = self._get_matching_files(folder)
            
            # Enforce max files limit
            self._enforce_max_files(folder, current_files)
            
            # Process each file
            for file_path in current_files:
                if not self.is_running:
                    break
                    
                self._process_file(folder, file_path)
                
        except Exception as e:
            logger.error(f"Error processing folder {folder.path}: {e}")
    
    def _get_matching_files(self, folder: MonitoredFolder) -> List[str]:
        """Get files matching the folder's include/exclude patterns or rotation settings."""
        files = []
        
        # If rotation_base is specified, use rotation file logic
        if folder.rotation_base:
            # Build explicit rotation file list: base, base.1, base.2, ..., base.N
            base_file = os.path.join(folder.path, folder.rotation_base)
            if os.path.exists(base_file):
                files.append(base_file)
            
            for i in range(1, folder.rotation_max + 1):
                rotation_file = f"{base_file}.{i}"
                if os.path.exists(rotation_file):
                    files.append(rotation_file)
            
            # Sort by modification time (newest first) - base file is usually newest
            files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        else:
            # Use traditional include/exclude patterns
            include_patterns = [p.strip() for p in folder.include_patterns.split(',') if p.strip()]
            
            for pattern in include_patterns:
                pattern_path = os.path.join(folder.path, pattern)
                matching_files = glob.glob(pattern_path)
                files.extend(matching_files)
            
            # Remove duplicates and sort by modification time (newest first)
            files = list(set(files))
            files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
            
            # Apply exclude patterns if any
            if folder.exclude_patterns:
                exclude_patterns = [p.strip() for p in folder.exclude_patterns.split(',') if p.strip()]
                for pattern in exclude_patterns:
                    pattern_path = os.path.join(folder.path, pattern)
                    exclude_files = set(glob.glob(pattern_path))
                    files = [f for f in files if f not in exclude_files]
        
        return files
    
    def _enforce_max_files(self, folder: MonitoredFolder, current_files: List[str]):
        """Enforce max files limit by archiving/deleting oldest files."""
        if len(current_files) <= folder.max_files:
            return
            
        # Keep only the newest max_files
        files_to_keep = current_files[:folder.max_files]
        files_to_remove = current_files[folder.max_files:]
        
        for file_path in files_to_remove:
            try:
                # Remove file state from database
                file_state = MonitoredFileState.query.filter_by(
                    folder_id=folder.id, 
                    path=file_path
                ).first()
                if file_state:
                    db.session.delete(file_state)
                
                # Clean up TailParser instance for this file
                if file_path in self.tail_parsers:
                    del self.tail_parsers[file_path]
                    logger.debug(f"Cleaned up TailParser instance for {file_path}")
                
                # For now, just log that we would delete/archive
                # In production, you might want to move to archive folder
                logger.info(f"Would archive/delete old file: {file_path}")
                
                db.session.commit()
                
            except Exception as e:
                logger.error(f"Error removing old file {file_path}: {e}")
                db.session.rollback()
    
    def _process_file(self, folder: MonitoredFolder, file_path: str):
        """Process a single file incrementally."""
        try:
            # Get or create file state
            file_state = MonitoredFileState.query.filter_by(
                folder_id=folder.id,
                path=file_path
            ).first()
            
            if not file_state:
                file_state = MonitoredFileState()
                file_state.folder_id = folder.id
                file_state.path = file_path
                file_state.last_size = 0
                file_state.last_offset = 0
                file_state.generation = 1
                db.session.add(file_state)
                db.session.commit()
            
            # Get or create file-specific TailParser instance
            if file_path not in self.tail_parsers:
                self.tail_parsers[file_path] = TailParser()
                logger.debug(f"Created new TailParser instance for {file_path}")
            
            tail_parser = self.tail_parsers[file_path]
            
            # Get file stats
            stat = os.stat(file_path)
            current_size = stat.st_size
            current_mtime = datetime.fromtimestamp(stat.st_mtime)
            current_inode = stat.st_ino
            
            # Check if file was rotated/truncated
            if (current_inode != file_state.inode and file_state.inode is not None) or \
               current_size < file_state.last_size:
                logger.info(f"File rotation detected for {file_path}")
                file_state.last_offset = 0
                file_state.generation += 1
                # Reset only this file's TailParser buffer
                tail_parser.reset_buffer()
            
            # Update file state
            file_state.inode = current_inode
            file_state.last_mtime = current_mtime
            file_state.last_seen = datetime.utcnow()
            
            # Parse new content if file has grown
            if current_size > file_state.last_offset:
                records, new_offset, error = tail_parser.parse_file_tail(
                    file_path, file_state.last_offset
                )
                
                if error:
                    file_state.last_error = error
                    logger.error(f"Error parsing {file_path}: {error}")
                else:
                    file_state.last_error = None
                    
                    # Save records to database
                    if records:
                        saved_count = tail_parser.save_records_batch(records)
                        file_state.records_processed += saved_count
                        logger.info(f"Processed {saved_count} records from {file_path}")
                
                # Update offset
                file_state.last_offset = new_offset
                file_state.last_size = current_size
            
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            db.session.rollback()

# Global monitor instance
_monitor = None

def get_monitor() -> FolderMonitor:
    """Get the global monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = FolderMonitor()
    return _monitor

def start_monitor() -> bool:
    """Start the folder monitor service."""
    monitor = get_monitor()
    result = monitor.start()
    if result:
        logger.info(f"Monitor service started successfully (PID: {monitor.process_id}, Worker: {monitor.worker_id})")
    else:
        logger.warning("Failed to start monitor service - another instance may be running")
    return result

def stop_monitor():
    """Stop the folder monitor service across all workers."""
    monitor = get_monitor()
    logger.info("Stopping monitor service across all workers...")
    monitor.stop()
    
    # Also directly signal stop via database for any running instances
    try:
        with app.app_context():
            instance = db.session.query(MonitorInstance).filter_by(
                id="monitor"
            ).with_for_update().first()
            
            if instance and instance.active:
                instance.stop_requested = True
                instance.heartbeat_at = datetime.utcnow()
                db.session.commit()
                logger.info("Global stop signal sent to all monitor instances")
            else:
                logger.info("No active monitor instances found")
                
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to send global stop signal: {e}")

def is_monitor_running() -> bool:
    """Check if the monitor is currently running (checks both local and database state)."""
    monitor = get_monitor()
    
    # Check local state first
    if monitor.is_running:
        return True
    
    # Check database state for any active instances
    try:
        with app.app_context():
            instance = MonitorInstance.query.filter_by(id="monitor").first()
            if instance and instance.active:
                # Check if instance is stale
                if instance.heartbeat_at:
                    time_since_heartbeat = datetime.utcnow() - instance.heartbeat_at
                    return time_since_heartbeat < timedelta(seconds=60)
            return False
    except Exception as e:
        logger.error(f"Error checking monitor status: {e}")
        return False
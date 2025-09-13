import os
import re
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from xml.etree import ElementTree as ET

from log_parser import ReflixLogParser
from models import db, ReflixTracking

logger = logging.getLogger(__name__)

class TailParser:
    """
    Incremental parser for REFLIV log files that reads only new content
    and maintains state between reads to avoid reprocessing.
    """
    
    def __init__(self, buffer_size: int = 256 * 1024):  # 256KB buffer
        self.buffer_size = buffer_size
        self.sliding_buffer = ""
        self.reflix_parser = ReflixLogParser()
        
        # Regex patterns for finding REFLIV calls and XML blocks
        self.reflix_call_pattern = re.compile(
            r'Call for REFLIV <([^>]+)> at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'
        )
        self.xml_block_pattern = re.compile(
            r'<root[^>]*>.*?</root>', 
            re.DOTALL | re.MULTILINE
        )
    
    def parse_file_tail(self, file_path: str, last_offset: int = 0) -> Tuple[List[Dict], int, Optional[str]]:
        """
        Parse new content from a file starting at last_offset.
        
        Returns:
            - List of extracted tracking records
            - New file offset for next read
            - Error message if any
        """
        try:
            # Check if file exists and get current stats
            if not os.path.exists(file_path):
                return [], last_offset, f"File not found: {file_path}"
            
            stat = os.stat(file_path)
            current_size = stat.st_size
            
            # Handle file truncation or rotation (size smaller than last offset)
            if current_size < last_offset:
                logger.info(f"File {file_path} appears truncated or rotated. Resetting offset.")
                last_offset = 0
                self.sliding_buffer = ""  # Clear buffer on rotation
            
            # Nothing to read if we're at the end
            if current_size == last_offset:
                return [], last_offset, None
            
            # Read new content
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(last_offset)
                new_content = f.read()
                new_offset = f.tell()
            
            if not new_content:
                return [], last_offset, None
            
            # Update sliding buffer
            self.sliding_buffer += new_content
            
            # Keep buffer size manageable
            if len(self.sliding_buffer) > self.buffer_size * 2:
                # Keep only the last buffer_size worth of data
                self.sliding_buffer = self.sliding_buffer[-self.buffer_size:]
            
            # Extract tracking records from buffer
            records = self._extract_records_from_buffer(file_path)
            
            logger.info(f"Parsed {len(records)} records from {file_path} (offset {last_offset} -> {new_offset})")
            return records, new_offset, None
            
        except Exception as e:
            error_msg = f"Error parsing file tail {file_path}: {str(e)}"
            logger.error(error_msg)
            return [], last_offset, error_msg
    
    def _extract_records_from_buffer(self, log_file_name: str) -> List[Dict]:
        """
        Extract complete REFLIV tracking records from the sliding buffer.
        """
        records = []
        
        # Find all complete XML blocks in the buffer
        xml_matches = list(self.xml_block_pattern.finditer(self.sliding_buffer))
        
        for xml_match in xml_matches:
            xml_content = xml_match.group(0)
            xml_start_pos = xml_match.start()
            
            # Look backward from XML start to find the nearest REFLIV call
            buffer_before_xml = self.sliding_buffer[:xml_start_pos]
            
            # Find the most recent REFLIV call before this XML
            call_matches = list(self.reflix_call_pattern.finditer(buffer_before_xml))
            if not call_matches:
                continue
            
            # Get the last (most recent) REFLIV call
            last_call = call_matches[-1]
            reference_number = last_call.group(1)
            call_timestamp_str = last_call.group(2)
            
            try:
                # Parse the timestamp
                call_timestamp = datetime.strptime(call_timestamp_str, '%Y-%m-%d %H:%M:%S')
                
                # Parse the XML to extract tracking data
                xml_records = self.reflix_parser._parse_xml_response(
                    xml_content, reference_number, log_file_name, call_timestamp
                )
                
                records.extend(xml_records)
                
            except Exception as e:
                logger.warning(f"Failed to parse XML block for ref {reference_number}: {e}")
                continue
        
        # Remove processed content from buffer to avoid reprocessing
        if xml_matches:
            # Keep only content after the last processed XML block
            last_xml_end = xml_matches[-1].end()
            self.sliding_buffer = self.sliding_buffer[last_xml_end:]
        
        return records
    
    def save_records_batch(self, records: List[Dict], batch_size: int = 100) -> int:
        """
        Save tracking records to database in batches with duplicate handling.
        
        Returns number of records actually saved.
        """
        if not records:
            return 0
        
        saved_count = 0
        
        try:
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                
                for record_data in batch:
                    try:
                        # Create new tracking record
                        tracking = ReflixTracking(**record_data)
                        db.session.add(tracking)
                        saved_count += 1
                        
                    except Exception as e:
                        # Handle duplicate or other constraint errors
                        logger.debug(f"Skipped duplicate record: {e}")
                        db.session.rollback()
                        continue
                
                # Commit batch
                try:
                    db.session.commit()
                    logger.debug(f"Committed batch of {len(batch)} records")
                except Exception as e:
                    logger.warning(f"Batch commit failed: {e}")
                    db.session.rollback()
                    saved_count -= len(batch)
            
            logger.info(f"Successfully saved {saved_count} new tracking records")
            return saved_count
            
        except Exception as e:
            logger.error(f"Error saving records batch: {e}")
            db.session.rollback()
            return 0
    
    def reset_buffer(self):
        """Reset the internal buffer - useful when starting to monitor a new file."""
        self.sliding_buffer = ""
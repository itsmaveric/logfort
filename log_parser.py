import re
import xml.etree.ElementTree as ET
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ReflixLogParser:
    def __init__(self):
        # Regex pattern to match REFLIV calls with reference numbers
        self.reflix_pattern = r'Call for REFLIV\s+([A-Z]\d{10})'
        # Pattern to extract XML response data
        self.xml_pattern = r'<root>.*?</root>'
        
    def parse_log_file(self, file_content, filename):
        """
        Parse a log file and extract REFLIV tracking data
        
        Args:
            file_content (str): Content of the log file
            filename (str): Name of the log file
            
        Returns:
            list: List of tracking records
        """
        records = []
        lines = file_content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Look for REFLIV call
            reflix_match = re.search(self.reflix_pattern, line)
            if reflix_match:
                reference_number = reflix_match.group(1)
                log_timestamp = self._extract_timestamp_from_line(line)
                
                # Look for XML response in subsequent lines
                xml_data = self._find_xml_response(lines, i)
                if xml_data:
                    tracking_records = self._parse_xml_response(
                        xml_data, reference_number, filename, log_timestamp
                    )
                    records.extend(tracking_records)
                    
            i += 1
            
        return records
    
    def _extract_timestamp_from_line(self, line):
        """Extract timestamp from log line"""
        try:
            # Pattern: 2025-09-08 10:26:48.955
            timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})', line)
            if timestamp_match:
                timestamp_str = timestamp_match.group(1)
                return datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
        except Exception as e:
            logger.warning(f"Could not parse timestamp from line: {line}. Error: {e}")
        
        return datetime.now()  # Use naive datetime
    
    def _find_xml_response(self, lines, start_index):
        """Find XML response starting from the given index"""
        xml_lines = []
        in_xml = False
        
        for i in range(start_index, min(start_index + 100, len(lines))):  # Look within next 100 lines
            line = lines[i].strip()
            
            if '<root>' in line:
                in_xml = True
                # Extract the XML part from the line
                xml_start = line.find('<root>')
                xml_part = line[xml_start:]
                xml_lines.append(xml_part)
                
                # Check if </root> is also on the same line
                if '</root>' in xml_part:
                    break
            elif in_xml:
                # Clean the line - remove log prefixes
                clean_line = self._clean_log_line(line)
                if clean_line:
                    xml_lines.append(clean_line)
                    
                if '</root>' in line:
                    break
                    
        if xml_lines and in_xml:
            xml_content = '\n'.join(xml_lines)
            # Ensure we have complete XML
            if '<root>' in xml_content and '</root>' in xml_content:
                return xml_content
        return None
    
    def _clean_log_line(self, line):
        """Clean log line to extract XML content"""
        # Remove timestamp and log level prefixes
        # Pattern: 2025-09-08 10:26:49.086 INFO  ResponseHandler:489 - [main] 
        if ' - [main] ' in line:
            parts = line.split(' - [main] ', 1)
            if len(parts) > 1:
                return parts[1].strip()
        
        # If no prefix pattern found, return the line as is (might be pure XML)
        return line.strip() if line.strip() else None
    
    def _parse_xml_response(self, xml_data, reference_number, filename, log_timestamp):
        """Parse XML response and extract tracking data"""
        records = []
        
        try:
            # Log the XML data for debugging
            logger.debug(f"Parsing XML for reference {reference_number}: {xml_data[:200]}...")
            
            root = ET.fromstring(xml_data)
            
            # Only check for main stateData (overall order status)
            main_state_data = root.find('.//requestedData/stateData')
            if main_state_data is not None:
                record = self._extract_state_record(
                    main_state_data, reference_number, None, filename, log_timestamp
                )
                if record:
                    records.append(record)
                        
        except ET.ParseError as e:
            logger.error(f"XML parsing error for reference {reference_number}: {e}")
            logger.debug(f"Failed XML content: {xml_data}")
        except Exception as e:
            logger.error(f"Unexpected error parsing XML for reference {reference_number}: {e}")
            
        return records
    
    def _extract_state_record(self, state_element, reference_number, unit_ref, filename, log_timestamp):
        """Extract a single state record from XML element"""
        try:
            title_elem = state_element.find('title')
            desc_elem = state_element.find('descriptionText')
            timestamp_elem = state_element.find('timestamp')
            location_elem = state_element.find('location')
            
            if title_elem is None:
                return None
                
            status = title_elem.text
            description = desc_elem.text if desc_elem is not None else None
            location = location_elem.text if location_elem is not None and location_elem.text else None
            
            # Parse timestamp
            timestamp = None
            if timestamp_elem is not None and timestamp_elem.text:
                try:
                    # Parse ISO format: 2025-09-01T14:00:00.448Z
                    timestamp_str = timestamp_elem.text
                    if timestamp_str.endswith('Z'):
                        timestamp_str = timestamp_str[:-1] + '+00:00'
                    timestamp = datetime.fromisoformat(timestamp_str)
                    # Convert to naive datetime for SQLAlchemy compatibility
                    if timestamp.tzinfo is not None:
                        timestamp = timestamp.replace(tzinfo=None)
                except ValueError:
                    logger.warning(f"Could not parse timestamp: {timestamp_elem.text}")
                    timestamp = log_timestamp
            else:
                timestamp = log_timestamp
                
            return {
                'reference_number': reference_number,
                'shipping_unit_ref': unit_ref,
                'status': status,
                'description': description,
                'timestamp': timestamp,
                'location': location,
                'log_file_name': filename,
                'log_timestamp': log_timestamp
            }
            
        except Exception as e:
            logger.error(f"Error extracting state record: {e}")
            return None

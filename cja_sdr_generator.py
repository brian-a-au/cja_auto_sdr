import cjapy
import pandas as pd
import json
from datetime import datetime
import pytz
import logging
import sys
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# ==================== LOGGING SETUP ====================

def setup_logging(data_view_id: str) -> logging.Logger:
    """Setup logging to both file and console"""
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Create log filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f"SDR_Generation_{data_view_id}_{timestamp}.log"
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized. Log file: {log_file}")
    return logger

# Set the Data View id we want into a variable
data_view = "dv_677ea9291244fd082f02dd42"

# Initialize logging
logger = setup_logging(data_view)

# ==================== PERFORMANCE TRACKING ====================

class PerformanceTracker:
    """Track execution time for operations"""
    def __init__(self, logger: logging.Logger):
        self.metrics = {}
        self.logger = logger
        self.start_times = {}
    
    def start(self, operation_name: str):
        """Start timing an operation"""
        self.start_times[operation_name] = time.time()
    
    def end(self, operation_name: str):
        """End timing an operation"""
        if operation_name in self.start_times:
            duration = time.time() - self.start_times[operation_name]
            self.metrics[operation_name] = duration
            self.logger.info(f"⏱️  {operation_name} completed in {duration:.2f}s")
            del self.start_times[operation_name]
    
    def get_summary(self) -> str:
        """Generate performance summary"""
        if not self.metrics:
            return "No performance metrics collected"
        
        total = sum(self.metrics.values())
        lines = ["", "=" * 60, "PERFORMANCE SUMMARY", "=" * 60]
        
        for operation, duration in sorted(self.metrics.items(), key=lambda x: x[1], reverse=True):
            percentage = (duration / total) * 100 if total > 0 else 0
            lines.append(f"{operation:35s}: {duration:6.2f}s ({percentage:5.1f}%)")
        
        lines.extend(["=" * 60, f"{'Total Execution Time':35s}: {total:6.2f}s", "=" * 60])
        return "\n".join(lines)

# Initialize performance tracker
perf_tracker = PerformanceTracker(logger)

# ==================== CJA INITIALIZATION ====================

def validate_config_file(config_file: str) -> bool:
    """Validate configuration file exists and has required structure"""
    try:
        logger.info(f"Validating configuration file: {config_file}")
        
        config_path = Path(config_file)
        
        # Check if file exists
        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path.absolute()}")
            logger.error(f"Please ensure '{config_file}' exists in the current directory")
            return False
        
        # Check if file is readable
        if not config_path.is_file():
            logger.error(f"'{config_file}' is not a valid file")
            return False
        
        # Validate JSON structure
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            # Check for required fields in config
            required_fields = ['org_id', 'client_id', 'tech_id', 'secret', 'private_key']
            missing_fields = [field for field in required_fields if field not in config_data]
            
            if missing_fields:
                logger.warning(f"Configuration file may be missing required fields: {', '.join(missing_fields)}")
                logger.warning("This may cause authentication failures")
            else:
                logger.info("Configuration file structure validated successfully")
            
            # Check for empty values
            empty_fields = [field for field in required_fields if field in config_data and not config_data[field]]
            if empty_fields:
                logger.warning(f"Configuration file has empty values for: {', '.join(empty_fields)}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Configuration file is not valid JSON: {str(e)}")
            logger.error("Please check the file format and ensure it's properly formatted JSON")
            return False
        except Exception as e:
            logger.warning(f"Could not fully validate config structure: {str(e)}")
            logger.info("Proceeding with initialization attempt...")
        
        return True
        
    except Exception as e:
        logger.error(f"Unexpected error validating config file: {str(e)}")
        return False

def initialize_cja(config_file: str = "myconfig.json") -> Optional[cjapy.CJA]:
    """Initialize CJA connection with comprehensive error handling"""
    try:
        logger.info("=" * 60)
        logger.info("INITIALIZING CJA CONNECTION")
        logger.info("=" * 60)
        
        # Validate config file first
        if not validate_config_file(config_file):
            logger.critical("Configuration file validation failed")
            logger.critical("Please create a valid config file with the following structure:")
            logger.critical(json.dumps({
                "org_id": "your_org_id",
                "client_id": "your_client_id", 
                "tech_id": "your_tech_account_id",
                "secret": "your_client_secret",
                "private_key": "path/to/private.key"
            }, indent=2))
            return None
        
        # Attempt to import config
        logger.info("Loading CJA configuration...")
        cjapy.importConfigFile(config_file)
        logger.info("Configuration loaded successfully")
        
        # Attempt to create CJA instance
        logger.info("Creating CJA instance...")
        cja = cjapy.CJA()
        logger.info("CJA instance created successfully")
        
        # Test connection with a simple API call
        logger.info("Testing API connection...")
        try:
            # Attempt to list data views to verify connection
            test_call = cja.getDataViews()
            if test_call is not None:
                logger.info(f"✓ API connection successful! Found {len(test_call) if hasattr(test_call, '__len__') else 'multiple'} data view(s)")
            else:
                logger.warning("API connection test returned None - connection may be unstable")
        except Exception as test_error:
            logger.warning(f"Could not verify connection with test call: {str(test_error)}")
            logger.warning("Proceeding anyway - errors may occur during data fetching")
        
        logger.info("CJA initialization complete")
        return cja
        
    except FileNotFoundError as e:
        logger.critical("=" * 60)
        logger.critical("CONFIGURATION FILE ERROR")
        logger.critical("=" * 60)
        logger.critical(f"Config file not found: {config_file}")
        logger.critical(f"Current working directory: {Path.cwd()}")
        logger.critical("Please ensure the configuration file exists in the correct location")
        return None
        
    except ImportError as e:
        logger.critical("=" * 60)
        logger.critical("DEPENDENCY ERROR")
        logger.critical("=" * 60)
        logger.critical(f"Failed to import cjapy module: {str(e)}")
        logger.critical("Please ensure cjapy is installed: pip install cjapy")
        return None
        
    except AttributeError as e:
        logger.critical("=" * 60)
        logger.critical("CJA CONFIGURATION ERROR")
        logger.critical("=" * 60)
        logger.critical(f"Configuration error: {str(e)}")
        logger.critical("This usually indicates an issue with the authentication credentials")
        logger.critical("Please verify all fields in your configuration file are correct")
        return None
        
    except PermissionError as e:
        logger.critical("=" * 60)
        logger.critical("PERMISSION ERROR")
        logger.critical("=" * 60)
        logger.critical(f"Cannot read configuration file: {str(e)}")
        logger.critical("Please check file permissions")
        return None
        
    except Exception as e:
        logger.critical("=" * 60)
        logger.critical("CJA INITIALIZATION FAILED")
        logger.critical("=" * 60)
        logger.critical(f"Unexpected error: {str(e)}")
        logger.critical(f"Error type: {type(e).__name__}")
        logger.exception("Full error details:")
        logger.critical("")
        logger.critical("Troubleshooting steps:")
        logger.critical("1. Verify your configuration file exists and is valid JSON")
        logger.critical("2. Check that all authentication credentials are correct")
        logger.critical("3. Ensure your API credentials have the necessary permissions")
        logger.critical("4. Verify you have network connectivity to Adobe services")
        logger.critical("5. Check if cjapy library is up to date: pip install --upgrade cjapy")
        return None

# Initialize CJA with comprehensive error handling
cja = initialize_cja()

if cja is None:
    logger.critical("=" * 60)
    logger.critical("FATAL ERROR: Cannot proceed without CJA connection")
    logger.critical("=" * 60)
    logger.critical("Script execution terminated")
    logger.critical(f"Please check the log file for details: {Path('logs').absolute()}")
    sys.exit(1)

logger.info("✓ CJA connection established successfully")

# ==================== DATA VIEW VALIDATION ====================

def validate_data_view(cja: cjapy.CJA, data_view_id: str) -> bool:
    """Validate that the data view exists and is accessible with detailed error reporting"""
    try:
        logger.info("=" * 60)
        logger.info("VALIDATING DATA VIEW")
        logger.info("=" * 60)
        logger.info(f"Data View ID: {data_view_id}")
        
        # Basic format validation
        if not data_view_id or not isinstance(data_view_id, str):
            logger.error("Invalid data view ID format")
            logger.error("Data view ID must be a non-empty string")
            return False
        
        if not data_view_id.startswith('dv_'):
            logger.warning(f"Data view ID '{data_view_id}' does not follow standard format (dv_...)")
            logger.warning("This may still be valid, but unusual")
        
        # Attempt to fetch data view info
        logger.info("Fetching data view information from API...")
        try:
            dv_info = cja.getDataView(data_view_id)
        except AttributeError as e:
            logger.error("API method 'getDataView' not available")
            logger.error("This may indicate an outdated version of cjapy")
            logger.error("Please update cjapy: pip install --upgrade cjapy")
            return False
        except Exception as api_error:
            logger.error(f"API call failed: {str(api_error)}")
            logger.error("Possible reasons:")
            logger.error("  1. Data view does not exist")
            logger.error("  2. You don't have permission to access this data view")
            logger.error("  3. Network connectivity issues")
            logger.error("  4. API authentication has expired")
            return False
        
        # Validate response
        if not dv_info:
            logger.error(f"Data view '{data_view_id}' returned empty response")
            logger.error("This typically means:")
            logger.error("  - The data view does not exist")
            logger.error("  - You don't have access to this data view")
            logger.error("  - The data view ID is incorrect")
            
            # Try to list available data views to help user
            logger.info("Attempting to list available data views...")
            try:
                available_dvs = cja.getDataViews()
                if available_dvs and len(available_dvs) > 0:
                    logger.info(f"You have access to {len(available_dvs)} data view(s):")
                    for i, dv in enumerate(available_dvs[:10]):  # Show first 10
                        dv_id = dv.get('id', 'unknown')
                        dv_name = dv.get('name', 'unknown')
                        logger.info(f"  {i+1}. {dv_name} (ID: {dv_id})")
                    if len(available_dvs) > 10:
                        logger.info(f"  ... and {len(available_dvs) - 10} more")
                else:
                    logger.warning("No data views found - you may not have access to any data views")
            except Exception as list_error:
                logger.warning(f"Could not list available data views: {str(list_error)}")
            
            return False
        
        # Extract and validate data view details
        dv_name = dv_info.get('name', 'Unknown')
        dv_description = dv_info.get('description', 'No description')
        dv_owner = dv_info.get('owner', {}).get('name', 'Unknown')
        
        logger.info("✓ Data view validated successfully!")
        logger.info(f"  Name: {dv_name}")
        logger.info(f"  ID: {data_view_id}")
        logger.info(f"  Owner: {dv_owner}")
        if dv_description and dv_description != 'No description':
            logger.info(f"  Description: {dv_description[:100]}{'...' if len(dv_description) > 100 else ''}")
        
        # Additional validation checks
        warnings = []
        
        if 'components' in dv_info:
            components = dv_info.get('components', {})
            if not components.get('dimensions') and not components.get('metrics'):
                warnings.append("Data view appears to have no components defined")
        
        if warnings:
            logger.warning("Data view validation warnings:")
            for warning in warnings:
                logger.warning(f"  - {warning}")
        
        return True
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error("DATA VIEW VALIDATION ERROR")
        logger.error("=" * 60)
        logger.error(f"Unexpected error during validation: {str(e)}")
        logger.exception("Full error details:")
        logger.error("")
        logger.error("Please verify:")
        logger.error("  1. The data view ID is correct")
        logger.error("  2. You have access to this data view")
        logger.error("  3. Your API credentials are valid")
        return False

# Validate data view before proceeding
if not validate_data_view(cja, data_view):
    logger.critical("=" * 60)
    logger.critical("FATAL ERROR: Data view validation failed")
    logger.critical("=" * 60)
    logger.critical(f"Cannot proceed with invalid data view: {data_view}")
    logger.critical("")
    logger.critical("Please check:")
    logger.critical("  1. Verify the data view ID is correct")
    logger.critical("  2. Ensure you have permission to access this data view")
    logger.critical("  3. Confirm the data view exists in your organization")
    logger.critical("")
    logger.critical("Script execution terminated")
    sys.exit(1)

logger.info("✓ Data view validation complete - proceeding with data fetch")

# ==================== OPTIMIZED API DATA FETCHING ====================

class ParallelAPIFetcher:
    """Fetch multiple API endpoints in parallel using threading"""
    
    def __init__(self, cja: cjapy.CJA, logger: logging.Logger, max_workers: int = 3):
        self.cja = cja
        self.logger = logger
        self.max_workers = max_workers
    
    def fetch_all_data(self, data_view_id: str) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
        """
        Fetch metrics, dimensions, and data view info in parallel
        
        Returns:
            Tuple of (metrics_df, dimensions_df, dataview_info)
        """
        self.logger.info("Starting parallel data fetch operations...")
        perf_tracker.start("Parallel API Fetch")
        
        results = {
            'metrics': None,
            'dimensions': None,
            'dataview': None
        }
        
        errors = {}
        
        # Define fetch tasks
        tasks = {
            'metrics': lambda: self._fetch_metrics(data_view_id),
            'dimensions': lambda: self._fetch_dimensions(data_view_id),
            'dataview': lambda: self._fetch_dataview_info(data_view_id)
        }
        
        # Execute tasks in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_name = {
                executor.submit(task): name 
                for name, task in tasks.items()
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_name):
                task_name = future_to_name[future]
                try:
                    results[task_name] = future.result()
                    self.logger.info(f"✓ {task_name.capitalize()} fetch completed")
                except Exception as e:
                    errors[task_name] = str(e)
                    self.logger.error(f"✗ {task_name.capitalize()} fetch failed: {e}")
        
        perf_tracker.end("Parallel API Fetch")
        
        # Log summary
        success_count = sum(1 for v in results.values() if v is not None)
        self.logger.info(f"Parallel fetch complete: {success_count}/3 successful")
        
        if errors:
            self.logger.warning(f"Errors encountered: {list(errors.keys())}")
        
        # Return results with proper None checking for DataFrames
        metrics_result = results.get('metrics')
        dimensions_result = results.get('dimensions')
        dataview_result = results.get('dataview')
        
        # Handle DataFrame None checks properly
        if metrics_result is None or (isinstance(metrics_result, pd.DataFrame) and metrics_result.empty):
            metrics_result = pd.DataFrame()
        
        if dimensions_result is None or (isinstance(dimensions_result, pd.DataFrame) and dimensions_result.empty):
            dimensions_result = pd.DataFrame()
        
        if dataview_result is None:
            dataview_result = {}
        
        return metrics_result, dimensions_result, dataview_result
    
    def _fetch_metrics(self, data_view_id: str) -> pd.DataFrame:
        """Fetch metrics with error handling"""
        try:
            self.logger.debug(f"Fetching metrics for {data_view_id}")
            metrics = self.cja.getMetrics(data_view_id, inclType=True, full=True)
            
            if metrics is None or (isinstance(metrics, pd.DataFrame) and metrics.empty):
                self.logger.warning("No metrics returned from API")
                return pd.DataFrame()
            
            self.logger.info(f"Successfully fetched {len(metrics)} metrics")
            return metrics
            
        except AttributeError as e:
            self.logger.error(f"API method error - getMetrics may not be available: {str(e)}")
            return pd.DataFrame()
        except Exception as e:
            self.logger.error(f"Failed to fetch metrics: {str(e)}")
            return pd.DataFrame()
    
    def _fetch_dimensions(self, data_view_id: str) -> pd.DataFrame:
        """Fetch dimensions with error handling"""
        try:
            self.logger.debug(f"Fetching dimensions for {data_view_id}")
            dimensions = self.cja.getDimensions(data_view_id, inclType=True, full=True)
            
            if dimensions is None or (isinstance(dimensions, pd.DataFrame) and dimensions.empty):
                self.logger.warning("No dimensions returned from API")
                return pd.DataFrame()
            
            self.logger.info(f"Successfully fetched {len(dimensions)} dimensions")
            return dimensions
            
        except AttributeError as e:
            self.logger.error(f"API method error - getDimensions may not be available: {str(e)}")
            return pd.DataFrame()
        except Exception as e:
            self.logger.error(f"Failed to fetch dimensions: {str(e)}")
            return pd.DataFrame()
    
    def _fetch_dataview_info(self, data_view_id: str) -> dict:
        """Fetch data view information with error handling"""
        try:
            self.logger.debug(f"Fetching data view information for {data_view_id}")
            lookup_data = self.cja.getDataView(data_view_id)
            
            if not lookup_data:
                self.logger.error("Data view information returned empty")
                return {"name": "Unknown", "id": data_view_id}
            
            self.logger.info(f"Successfully fetched data view info: {lookup_data.get('name', 'Unknown')}")
            return lookup_data
            
        except Exception as e:
            self.logger.error(f"Failed to fetch data view information: {str(e)}")
            return {"name": "Unknown", "id": data_view_id, "error": str(e)}

def fetch_metrics(cja: cjapy.CJA, data_view_id: str) -> pd.DataFrame:
    """Legacy function - kept for backward compatibility"""
    fetcher = ParallelAPIFetcher(cja, logger)
    return fetcher._fetch_metrics(data_view_id)

def fetch_dimensions(cja: cjapy.CJA, data_view_id: str) -> pd.DataFrame:
    """Legacy function - kept for backward compatibility"""
    fetcher = ParallelAPIFetcher(cja, logger)
    return fetcher._fetch_dimensions(data_view_id)

def fetch_dataview_info(cja: cjapy.CJA, data_view_id: str) -> dict:
    """Legacy function - kept for backward compatibility"""
    fetcher = ParallelAPIFetcher(cja, logger)
    return fetcher._fetch_dataview_info(data_view_id)

# Fetch all data with parallel optimization
logger.info("=" * 60)
logger.info("Starting optimized data fetch operations")
logger.info("=" * 60)

# Use parallel fetcher for optimal performance
fetcher = ParallelAPIFetcher(cja, logger, max_workers=3)
metrics, dimensions, lookup_data = fetcher.fetch_all_data(data_view)

# Check if we have any data to process
if metrics.empty and dimensions.empty:
    logger.critical("No metrics or dimensions fetched. Cannot generate SDR.")
    sys.exit(1)

logger.info("Data fetch operations completed successfully")

# ==================== DATA QUALITY VALIDATION ====================

class DataQualityChecker:
    def __init__(self, logger: logging.Logger):
        self.issues = []
        self.logger = logger
    
    def add_issue(self, severity: str, category: str, item_type: str, 
                  item_name: str, description: str, details: str = ""):
        """Add a data quality issue to the tracker"""
        self.issues.append({
            'Severity': severity,
            'Category': category,
            'Type': item_type,
            'Item Name': item_name,
            'Issue': description,
            'Details': details
        })
        self.logger.warning(f"DQ Issue [{severity}] - {item_type}: {description}")
    
    def check_duplicates(self, df: pd.DataFrame, item_type: str):
        """Check for duplicate names in metrics or dimensions"""
        try:
            if df.empty:
                self.logger.info(f"Skipping duplicate check for empty {item_type} dataframe")
                return
            
            if 'name' not in df.columns:
                self.logger.warning(f"'name' column not found in {item_type}. Skipping duplicate check.")
                return
            
            duplicates = df['name'].value_counts()
            duplicates = duplicates[duplicates > 1]
            
            for name, count in duplicates.items():
                self.add_issue(
                    severity='HIGH',
                    category='Duplicates',
                    item_type=item_type,
                    item_name=str(name),
                    description=f'Duplicate name found {count} times',
                    details=f'This {item_type.lower()} name appears {count} times in the data view'
                )
        except Exception as e:
            self.logger.error(f"Error checking duplicates for {item_type}: {str(e)}")
    
    def check_required_fields(self, df: pd.DataFrame, item_type: str, 
                            required_fields: List[str]):
        """Validate that required fields are present"""
        try:
            if df.empty:
                self.logger.info(f"Skipping required fields check for empty {item_type} dataframe")
                return
            
            missing_fields = [field for field in required_fields if field not in df.columns]
            
            if missing_fields:
                self.add_issue(
                    severity='CRITICAL',
                    category='Missing Fields',
                    item_type=item_type,
                    item_name='N/A',
                    description=f'Required fields missing from API response',
                    details=f'Missing fields: {", ".join(missing_fields)}'
                )
        except Exception as e:
            self.logger.error(f"Error checking required fields for {item_type}: {str(e)}")
    
    def check_null_values(self, df: pd.DataFrame, item_type: str, 
                         critical_fields: List[str]):
        """Check for null values in critical fields"""
        try:
            if df.empty:
                self.logger.info(f"Skipping null value check for empty {item_type} dataframe")
                return
            
            for field in critical_fields:
                if field in df.columns:
                    null_count = df[field].isna().sum()
                    if null_count > 0:
                        null_items = df[df[field].isna()]['name'].tolist() if 'name' in df.columns else []
                        self.add_issue(
                            severity='MEDIUM',
                            category='Null Values',
                            item_type=item_type,
                            item_name=', '.join(str(x) for x in null_items[:5]),
                            description=f'Null values in "{field}" field',
                            details=f'{null_count} item(s) missing {field}. Items: {", ".join(str(x) for x in null_items[:10])}'
                        )
        except Exception as e:
            self.logger.error(f"Error checking null values for {item_type}: {str(e)}")
    
    def check_missing_descriptions(self, df: pd.DataFrame, item_type: str):
        """Check for items without descriptions"""
        try:
            if df.empty:
                self.logger.info(f"Skipping description check for empty {item_type} dataframe")
                return
            
            if 'description' not in df.columns:
                self.logger.info(f"'description' column not found in {item_type}")
                return
            
            missing_desc = df[df['description'].isna() | (df['description'] == '')]
            
            if len(missing_desc) > 0:
                item_names = missing_desc['name'].tolist() if 'name' in missing_desc.columns else []
                self.add_issue(
                    severity='LOW',
                    category='Missing Descriptions',
                    item_type=item_type,
                    item_name=f'{len(missing_desc)} items',
                    description=f'{len(missing_desc)} items without descriptions',
                    details=f'Items: {", ".join(str(x) for x in item_names[:20])}'
                )
        except Exception as e:
            self.logger.error(f"Error checking descriptions for {item_type}: {str(e)}")
    
    def check_empty_dataframe(self, df: pd.DataFrame, item_type: str):
        """Check if dataframe is empty"""
        try:
            if df.empty:
                self.add_issue(
                    severity='CRITICAL',
                    category='Empty Data',
                    item_type=item_type,
                    item_name='N/A',
                    description=f'No {item_type.lower()} found in data view',
                    details=f'The API returned an empty dataset for {item_type.lower()}'
                )
        except Exception as e:
            self.logger.error(f"Error checking if {item_type} dataframe is empty: {str(e)}")
    
    def check_id_validity(self, df: pd.DataFrame, item_type: str):
        """Check for missing or invalid IDs"""
        try:
            if df.empty:
                self.logger.info(f"Skipping ID validity check for empty {item_type} dataframe")
                return
            
            if 'id' not in df.columns:
                self.logger.warning(f"'id' column not found in {item_type}")
                return
            
            missing_ids = df[df['id'].isna() | (df['id'] == '')]
            if len(missing_ids) > 0:
                self.add_issue(
                    severity='HIGH',
                    category='Invalid IDs',
                    item_type=item_type,
                    item_name=f'{len(missing_ids)} items',
                    description=f'{len(missing_ids)} items with missing or invalid IDs',
                    details='Items without valid IDs may cause issues in reporting'
                )
        except Exception as e:
            self.logger.error(f"Error checking ID validity for {item_type}: {str(e)}")
    
    def get_issues_dataframe(self) -> pd.DataFrame:
        """Return all issues as a DataFrame"""
        try:
            if not self.issues:
                self.logger.info("No data quality issues found")
                return pd.DataFrame({
                    'Severity': ['INFO'],
                    'Category': ['Data Quality'],
                    'Type': ['All'],
                    'Item Name': ['N/A'],
                    'Issue': ['No data quality issues detected'],
                    'Details': ['All validation checks passed successfully']
                })
            
            return pd.DataFrame(self.issues).sort_values(
                by=['Severity', 'Category'],
                ascending=[False, True]
            )
        except Exception as e:
            self.logger.error(f"Error creating issues dataframe: {str(e)}")
            return pd.DataFrame({
                'Severity': ['ERROR'],
                'Category': ['System'],
                'Type': ['Processing'],
                'Item Name': ['N/A'],
                'Issue': ['Error generating data quality report'],
                'Details': [str(e)]
            })

# Initialize data quality checker
logger.info("=" * 60)
logger.info("Starting data quality validation")
logger.info("=" * 60)

dq_checker = DataQualityChecker(logger)

# Required fields for validation
REQUIRED_METRIC_FIELDS = ['id', 'name', 'type']
REQUIRED_DIMENSION_FIELDS = ['id', 'name', 'type']
CRITICAL_FIELDS = ['id', 'name', 'title', 'description']

# Run all data quality checks
logger.info("Running comprehensive data quality checks...")

try:
    # Check if dataframes are empty
    dq_checker.check_empty_dataframe(metrics, 'Metrics')
    dq_checker.check_empty_dataframe(dimensions, 'Dimensions')
    
    # Check for required fields
    dq_checker.check_required_fields(metrics, 'Metrics', REQUIRED_METRIC_FIELDS)
    dq_checker.check_required_fields(dimensions, 'Dimensions', REQUIRED_DIMENSION_FIELDS)
    
    # Check for duplicates
    dq_checker.check_duplicates(metrics, 'Metrics')
    dq_checker.check_duplicates(dimensions, 'Dimensions')
    
    # Check for null values in critical fields
    dq_checker.check_null_values(metrics, 'Metrics', CRITICAL_FIELDS)
    dq_checker.check_null_values(dimensions, 'Dimensions', CRITICAL_FIELDS)
    
    # Check for missing descriptions
    dq_checker.check_missing_descriptions(metrics, 'Metrics')
    dq_checker.check_missing_descriptions(dimensions, 'Dimensions')
    
    # Check ID validity
    dq_checker.check_id_validity(metrics, 'Metrics')
    dq_checker.check_id_validity(dimensions, 'Dimensions')
    
    logger.info(f"Data quality checks complete. Found {len(dq_checker.issues)} issue(s)")
    
except Exception as e:
    logger.error(f"Error during data quality validation: {str(e)}")
    logger.info("Continuing with SDR generation despite validation errors")

# Get data quality issues dataframe
data_quality_df = dq_checker.get_issues_dataframe()

# ==================== DATA PROCESSING ====================

logger.info("=" * 60)
logger.info("Processing data for Excel export")
logger.info("=" * 60)

try:
    # Process lookup data into DataFrame
    logger.info("Processing data view lookup information...")
    lookup_data = {k: [v] if not isinstance(v, (list, tuple)) else v for k, v in lookup_data.items()}
    max_length = max(len(v) for v in lookup_data.values()) if lookup_data else 1
    lookup_data = {k: v + [None] * (max_length - len(v)) for k, v in lookup_data.items()}
    lookup_df = pd.DataFrame(lookup_data)
    logger.info(f"Processed lookup data with {len(lookup_df)} rows")
    
except Exception as e:
    logger.error(f"Error processing lookup data: {str(e)}")
    lookup_df = pd.DataFrame({'Error': ['Failed to process data view information']})

try:
    # Enhanced metadata creation
    logger.info("Creating metadata summary...")
    metric_types = metrics['type'].value_counts().to_dict() if not metrics.empty and 'type' in metrics.columns else {}
    metric_summary = [f"{type_}: {count}" for type_, count in metric_types.items()]
    
    dimension_types = dimensions['type'].value_counts().to_dict() if not dimensions.empty and 'type' in dimensions.columns else {}
    dimension_summary = [f"{type_}: {count}" for type_, count in dimension_types.items()]
    
    # Get current timezone and formatted timestamp
    local_tz = datetime.now().astimezone().tzinfo
    current_time = datetime.now(local_tz)
    formatted_timestamp = current_time.strftime('%Y-%m-%d %H:%M:%S %Z')
    
    # Count data quality issues by severity
    severity_counts = data_quality_df['Severity'].value_counts().to_dict()
    dq_summary = [f"{sev}: {count}" for sev, count in severity_counts.items()]
    
    # Create enhanced metadata DataFrame
    metadata_df = pd.DataFrame({
        'Property': [
            'Generated Date & timestamp and timezone',
            'Data View ID',
            'Data View Name',
            'Total Metrics',
            'Metrics Breakdown',
            'Total Dimensions',
            'Dimensions Breakdown',
            'Data Quality Issues',
            'Data Quality Summary'
        ],
        'Value': [
            formatted_timestamp,
            data_view,
            lookup_data.get("name", ["Unknown"])[0] if isinstance(lookup_data, dict) else "Unknown",
            len(metrics),
            '\n'.join(metric_summary) if metric_summary else 'No metrics found',
            len(dimensions),
            '\n'.join(dimension_summary) if dimension_summary else 'No dimensions found',
            len(dq_checker.issues),
            '\n'.join(dq_summary) if dq_summary else 'No issues'
        ]
    })
    logger.info("Metadata created successfully")
    
except Exception as e:
    logger.error(f"Error creating metadata: {str(e)}")
    metadata_df = pd.DataFrame({'Error': ['Failed to create metadata']})

# Function to format JSON cells
def format_json_cell(value):
    """Format JSON objects for Excel display"""
    try:
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2)
        return value
    except Exception as e:
        logger.warning(f"Error formatting JSON cell: {str(e)}")
        return str(value)

try:
    # Apply JSON formatting to all dataframes
    logger.info("Applying JSON formatting to dataframes...")
    
    for col in lookup_df.columns:
        lookup_df[col] = lookup_df[col].map(format_json_cell)
    
    if not metrics.empty:
        for col in metrics.columns:
            metrics[col] = metrics[col].map(format_json_cell)
    
    if not dimensions.empty:
        for col in dimensions.columns:
            dimensions[col] = dimensions[col].map(format_json_cell)
    
    logger.info("JSON formatting applied successfully")
    
except Exception as e:
    logger.error(f"Error applying JSON formatting: {str(e)}")

# Create Excel file name
try:
    dv_name = lookup_data.get("name", ["Unknown"])[0] if isinstance(lookup_data, dict) else "Unknown"
    # Sanitize filename
    dv_name = "".join(c for c in dv_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    excel_file_name = f'CJA_DataView_{dv_name}_{data_view}_SDR.xlsx'
    logger.info(f"Excel file will be saved as: {excel_file_name}")
except Exception as e:
    logger.error(f"Error creating filename: {str(e)}")
    excel_file_name = f'CJA_DataView_{data_view}_SDR.xlsx'

# ==================== EXCEL GENERATION ====================

# ==================== EXCEL GENERATION ====================

class OptimizedExcelWriter:
    """Optimized Excel writing with performance enhancements"""
    
    def __init__(self, filename: str, logger: logging.Logger):
        self.filename = filename
        self.logger = logger
        self.workbook = None
        self.writer = None
        self.formats = {}
    
    def __enter__(self):
        """Context manager entry"""
        self.writer = pd.ExcelWriter(
            self.filename,
            engine='xlsxwriter',
            engine_kwargs={'options': {
                'constant_memory': True,
                'nan_inf_to_errors': True
            }}
        )
        self.workbook = self.writer.book
        self._create_formats()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.writer:
            self.writer.close()
    
    def _create_formats(self):
        """Pre-create all formats to avoid repeated creation"""
        self.logger.debug("Creating Excel formats...")
        
        # Header format
        self.formats['header'] = self.workbook.add_format({
            'bold': True,
            'bg_color': '#366092',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'text_wrap': True
        })
        
        # Alternating row formats
        self.formats['grey'] = self.workbook.add_format({
            'bg_color': '#F2F2F2',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top'
        })
        
        self.formats['white'] = self.workbook.add_format({
            'bg_color': '#FFFFFF',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top'
        })
        
        # Data quality severity formats
        self.formats['critical'] = self.workbook.add_format({
            'bg_color': '#FFC7CE',
            'font_color': '#9C0006',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top'
        })
        
        self.formats['high'] = self.workbook.add_format({
            'bg_color': '#FFEB9C',
            'font_color': '#9C6500',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top'
        })
        
        self.formats['medium'] = self.workbook.add_format({
            'bg_color': '#C6EFCE',
            'font_color': '#006100',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top'
        })
        
        self.formats['low'] = self.workbook.add_format({
            'bg_color': '#DDEBF7',
            'font_color': '#1F4E78',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top'
        })
    
    def write_sheet(self, df: pd.DataFrame, sheet_name: str):
        """Write DataFrame to sheet with optimized formatting"""
        perf_tracker.start(f"Write Sheet: {sheet_name}")
        self.logger.debug(f"Writing sheet: {sheet_name} ({len(df)} rows)")
        
        try:
            # Write dataframe without index (faster)
            df.to_excel(self.writer, sheet_name=sheet_name, index=False)
            worksheet = self.writer.sheets[sheet_name]
            
            # Apply formatting efficiently
            self._format_headers(worksheet, df)
            self._format_columns(worksheet, df)
            self._format_rows(worksheet, df, sheet_name)
            
            # Add filters and freeze panes
            self._add_filters(worksheet, df)
            self._freeze_panes(worksheet)
            
            self.logger.debug(f"Sheet {sheet_name} written successfully")
            
        except Exception as e:
            self.logger.error(f"Error writing sheet {sheet_name}: {str(e)}")
            raise
        finally:
            perf_tracker.end(f"Write Sheet: {sheet_name}")
    
    def _format_headers(self, worksheet, df):
        """Format header row efficiently"""
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, self.formats['header'])
    
    def _format_columns(self, worksheet, df):
        """Set optimal column widths"""
        max_column_width = 100
        
        for idx, col in enumerate(df.columns):
            # Calculate column width based on content
            series = df[col]
            
            # Sample-based width calculation for large datasets
            if len(series) > 1000:
                sample_size = min(100, len(series))
                sample = series.sample(n=sample_size) if len(series) > sample_size else series
                max_len = max(
                    max(len(str(val).split('\n')[0]) for val in sample),
                    len(str(series.name))
                )
            else:
                max_len = max(
                    max(len(str(val).split('\n')[0]) for val in series) if len(series) > 0 else 0,
                    len(str(series.name))
                )
            
            # Set width with limits
            width = min(max_len + 2, max_column_width)
            worksheet.set_column(idx, idx, width)
    
    def _format_rows(self, worksheet, df, sheet_name):
        """Format data rows with appropriate styling"""
        # Determine if this is a data quality sheet
        is_dq_sheet = sheet_name == 'Data Quality' and 'Severity' in df.columns

        # Batch process rows for better performance
        for idx in range(len(df)):
            # Calculate row height based on content
            row_data = df.iloc[idx]
            max_lines = max(str(val).count('\n') for val in row_data) + 1
            row_height = min(max_lines * 15, 400)

            # Select format based on sheet type
            if is_dq_sheet:
                severity = row_data['Severity']
                if severity == 'CRITICAL':
                    row_format = self.formats['critical']
                elif severity == 'HIGH':
                    row_format = self.formats['high']
                elif severity == 'MEDIUM':
                    row_format = self.formats['medium']
                else:
                    row_format = self.formats['low']
            else:
                # Alternating row colors
                row_format = self.formats['grey'] if idx % 2 == 0 else self.formats['white']

            # Set row height
            worksheet.set_row(idx + 1, row_height)

            # Write each cell with the appropriate format
            for col_num, value in enumerate(row_data):
                worksheet.write(idx + 1, col_num, value, row_format)
    
    def _add_filters(self, worksheet, df):
        """Add autofilter to sheet"""
        if len(df) > 0:
            worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)
    
    def _freeze_panes(self, worksheet):
        """Freeze top row"""
        worksheet.freeze_panes(1, 0)

def apply_excel_formatting(writer, df, sheet_name):
    """Legacy function wrapper for backward compatibility"""
    try:
        logger.info(f"Formatting sheet: {sheet_name}")
        
        # Write dataframe to sheet
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        workbook = writer.book
        worksheet = writer.sheets[sheet_name]
        
        # Add formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#366092',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'text_wrap': True
        })
        
        grey_format = workbook.add_format({
            'bg_color': '#F2F2F2',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top'
        })
        
        white_format = workbook.add_format({
            'bg_color': '#FFFFFF',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top'
        })
        
        # Special formats for Data Quality sheet
        if sheet_name == 'Data Quality':
            critical_format = workbook.add_format({
                'bg_color': '#FFC7CE',
                'font_color': '#9C0006',
                'border': 1,
                'text_wrap': True,
                'align': 'top',
                'valign': 'top'
            })
            
            high_format = workbook.add_format({
                'bg_color': '#FFEB9C',
                'font_color': '#9C6500',
                'border': 1,
                'text_wrap': True,
                'align': 'top',
                'valign': 'top'
            })
            
            medium_format = workbook.add_format({
                'bg_color': '#C6EFCE',
                'font_color': '#006100',
                'border': 1,
                'text_wrap': True,
                'align': 'top',
                'valign': 'top'
            })
            
            low_format = workbook.add_format({
                'bg_color': '#DDEBF7',
                'font_color': '#1F4E78',
                'border': 1,
                'text_wrap': True,
                'align': 'top',
                'valign': 'top'
            })
        
        # Format header row
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        # Set row height and column width with text wrapping
        max_column_width = 100
        for idx, col in enumerate(df.columns):
            series = df[col]
            max_len = min(
                max(
                    max(len(str(val).split('\n')[0]) for val in series) if len(series) > 0 else 0,
                    len(str(series.name))
                ) + 2,
                max_column_width
            )
            worksheet.set_column(idx, idx, max_len)
        
        # Apply row formatting
        for idx in range(len(df)):
            max_lines = max(str(val).count('\n') for val in df.iloc[idx]) + 1
            row_height = min(max_lines * 15, 400)
            
            # Apply severity-based formatting for Data Quality sheet
            if sheet_name == 'Data Quality' and 'Severity' in df.columns:
                severity = df.iloc[idx]['Severity']
                if severity == 'CRITICAL':
                    row_format = critical_format
                elif severity == 'HIGH':
                    row_format = high_format
                elif severity == 'MEDIUM':
                    row_format = medium_format
                else:
                    row_format = low_format
            else:
                row_format = grey_format if idx % 2 == 0 else white_format
            
            worksheet.set_row(idx + 1, row_height, row_format)
        
        # Add autofilter to all sheets
        worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)
        
        # Freeze top row
        worksheet.freeze_panes(1, 0)
        
        logger.info(f"Successfully formatted sheet: {sheet_name}")
        
    except Exception as e:
        logger.error(f"Error formatting sheet {sheet_name}: {str(e)}")
        raise

# Write to Excel with optimization
logger.info("=" * 60)
logger.info("Generating Excel file")
logger.info("=" * 60)

try:
    logger.info(f"Creating Excel file: {excel_file_name}")
    perf_tracker.start("Total Excel Generation")
    
    # Use optimized Excel writer
    with OptimizedExcelWriter(excel_file_name, logger) as excel_writer:
        # Define sheets to write
        sheets_to_write = [
            (metadata_df, 'Metadata'),
            (data_quality_df, 'Data Quality'),
            (lookup_df, 'DataView'),
            (metrics, 'Metrics'),
            (dimensions, 'Dimensions')
        ]
        
        for sheet_data, sheet_name in sheets_to_write:
            try:
                if sheet_data.empty:
                    logger.warning(f"Sheet {sheet_name} is empty, creating placeholder")
                    placeholder_df = pd.DataFrame({'Note': [f'No data available for {sheet_name}']})
                    excel_writer.write_sheet(placeholder_df, sheet_name)
                else:
                    excel_writer.write_sheet(sheet_data, sheet_name)
            except Exception as e:
                logger.error(f"Failed to write sheet {sheet_name}: {str(e)}")
                # Continue with other sheets
                continue
    
    perf_tracker.end("Total Excel Generation")
    logger.info(f"✓ SDR generation complete! File saved as: {excel_file_name}")
    
    # Final summary
    logger.info("=" * 60)
    logger.info("EXECUTION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Data View: {dv_name} ({data_view})")
    logger.info(f"Metrics: {len(metrics)}")
    logger.info(f"Dimensions: {len(dimensions)}")
    logger.info(f"Data Quality Issues: {len(dq_checker.issues)}")
    
    if dq_checker.issues:
        logger.info("Data Quality Issues by Severity:")
        for severity, count in severity_counts.items():
            logger.info(f"  {severity}: {count}")
    
    logger.info(f"Output file: {excel_file_name}")
    logger.info("=" * 60)
    
except PermissionError as e:
    logger.critical(f"Permission denied writing to {excel_file_name}. File may be open in another program.")
    logger.critical("Please close the file and try again.")
    sys.exit(1)
except Exception as e:
    logger.critical(f"Failed to generate Excel file: {str(e)}")
    logger.exception("Full exception details:")
    sys.exit(1)

logger.info("Script execution completed successfully")

# Log performance summary
logger.info(perf_tracker.get_summary())
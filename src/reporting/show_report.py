import os
import hashlib
from pathlib import Path
from src.data.store import DataStore, Report
from sqlalchemy import select
from loguru import logger

def show_latest_report():
    store = DataStore()
    session = store.get_session()
    
    report = session.execute(
        select(Report).where(Report.type == 'daily').order_by(Report.date.desc()).limit(1)
    ).scalar_one_or_none()
    
    if report:
        print(f"--- Report ID: {report.report_id} ---")
        print(report.content_md)
        
        # Save to root directory
        save_report_to_root(report)
    else:
        print("No report found.")

def save_report_to_root(report):
    """Save report to root directory, only if content has changed."""
    try:
        # Get project root (3 levels up from this file)
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent
        
        # Output file path
        output_file = project_root / "LATEST_REPORT.md"
        
        print(f"\n[DEBUG] Project root: {project_root}")
        print(f"[DEBUG] Output file: {output_file}")
        
        # Compute hash of new content
        new_content = report.content_md
        new_hash = hashlib.md5(new_content.encode('utf-8')).hexdigest()
        
        # Check if file exists and compare hash
        should_save = True
        if output_file.exists():
            try:
                existing_content = output_file.read_text(encoding='utf-8')
                existing_hash = hashlib.md5(existing_content.encode('utf-8')).hexdigest()
                
                if existing_hash == new_hash:
                    should_save = False
                    logger.info(f"Report content unchanged, skipping save to {output_file.name}")
            except Exception as e:
                logger.warning(f"Failed to read existing report: {e}")
        
        if should_save:
            try:
                output_file.write_text(new_content, encoding='utf-8')
                logger.success(f"Report saved to {output_file}")
                print(f"\n✅ Report saved to: {output_file}")
            except Exception as e:
                logger.error(f"Failed to save report: {e}")
                print(f"\n❌ Failed to save report: {e}")
        else:
            print(f"\n📝 Report unchanged, not saving (existing: {output_file})")
    
    except Exception as e:
        logger.error(f"Failed to save report to root: {e}")
        print(f"\n❌ Error saving report: {e}")

if __name__ == "__main__":
    show_latest_report()

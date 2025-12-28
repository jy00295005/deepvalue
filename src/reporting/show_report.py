from src.data.store import DataStore, Report
from sqlalchemy import select

def show_latest_report():
    store = DataStore()
    session = store.get_session()
    
    report = session.execute(
        select(Report).where(Report.type == 'daily').order_by(Report.date.desc()).limit(1)
    ).scalar_one_or_none()
    
    if report:
        print(f"--- Report ID: {report.report_id} ---")
        print(report.content_md)
    else:
        print("No report found.")

if __name__ == "__main__":
    show_latest_report()

import datetime
import logging
import pandas as pd
from sqlalchemy import create_engine, inspect, text

logger = logging.getLogger(__name__)

DB_CONNECTION_STRING = "sqlite:///data/portfolio_database.db"


def get_db_engine():
    """Creates and returns a SQLAlchemy SQLite engine."""
    return create_engine(DB_CONNECTION_STRING)


def save_dataframe_to_db(df: pd.DataFrame, table_name: str, run_date: str = None):
    """Saves a pandas dataframe to a SQLite database table with an active run_date."""
    if df is None or df.empty:
        logger.warning(
            f"DataFrame for table '{table_name}' is empty. Skipping save."
        )
        return

    if run_date is None:
        run_date = datetime.date.today().strftime("%Y-%m-%d")

    # Make a copy to avoid SettingWithCopyWarning
    df_to_save = df.copy()
    df_to_save["run_date"] = run_date

    engine = get_db_engine()
    try:
        inspector = inspect(engine)
        
        # Check if table exists and if it already contains the 'run_date' column
        if inspector.has_table(table_name):
            columns = [col["name"] for col in inspector.get_columns(table_name)]
            if "run_date" not in columns:
                logger.info(f"Table '{table_name}' exists without 'run_date'. Recreating table to update schema...")
                df_to_save.to_sql(table_name, con=engine, if_exists="replace", index=False)
            else:
                # Table exists and has run_date; append today's data (or replace existing records for today)
                with engine.begin() as conn:
                    conn.execute(text(f"DELETE FROM {table_name} WHERE run_date = :rdate"), {"rdate": run_date})
                df_to_save.to_sql(table_name, con=engine, if_exists="append", index=False)
        else:
            # Table doesn't exist yet
            df_to_save.to_sql(table_name, con=engine, if_exists="replace", index=False)

        logger.info(
            f"Successfully saved {len(df_to_save)} rows to database table '{table_name}' for run date: {run_date}"
        )
    except Exception as e:
        logger.error(
            f"Failed to save table '{table_name}' to database: {e}",
            exc_info=True,
        )
        raise


def load_dataframe_from_db(table_name: str, run_date: str = None) -> pd.DataFrame:
    """Reads a pandas dataframe from a SQLite database table, optionally filtered by run_date."""
    engine = get_db_engine()
    try:
        inspector = inspect(engine)
        if not inspector.has_table(table_name):
            logger.warning(
                f"Database table '{table_name}' does not exist in SQLite."
            )
            return pd.DataFrame()

        if run_date:
            query = f"SELECT * FROM {table_name} WHERE run_date = '{run_date}'"
        else:
            # Default to the most recent run date available in the table
            query = f"SELECT * FROM {table_name} WHERE run_date = (SELECT MAX(run_date) FROM {table_name})"

        df = pd.read_sql(query, con=engine)
        logger.info(
            f"Successfully loaded {len(df)} rows from table '{table_name}' (Run Date: {run_date or 'Latest'})"
        )
        return df
    except Exception as e:
        logger.error(
            f"Failed to load table '{table_name}' from database: {e}",
            exc_info=True,
        )
        return pd.DataFrame()
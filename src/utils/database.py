import logging
import pandas as pd
from sqlalchemy import create_engine, inspect

logger = logging.getLogger(__name__)

DB_CONNECTION_STRING = "sqlite:///data/portfolio_database.db"


def get_db_engine():
    """Creates and returns a SQLAlchemy SQLite engine."""
    return create_engine(DB_CONNECTION_STRING)


def save_dataframe_to_db(df: pd.DataFrame, table_name: str):
    """Saves a pandas dataframe to a SQLite database table."""
    if df is None or df.empty:
        logger.warning(
            f"DataFrame for table '{table_name}' is empty. Skipping save."
        )
        return

    engine = get_db_engine()
    try:
        df.to_sql(table_name, con=engine, if_exists="replace", index=False)
        logger.info(
            f"Successfully saved {len(df)} rows to database table: '{table_name}'"
        )
    except Exception as e:
        logger.error(
            f"Failed to save table '{table_name}' to database: {e}",
            exc_info=True,
        )
        raise


def load_dataframe_from_db(table_name: str) -> pd.DataFrame:
    """Reads a pandas dataframe from a SQLite database table using SQLAlchemy 2.0 inspector."""
    engine = get_db_engine()
    try:
        inspector = inspect(engine)
        if not inspector.has_table(table_name):
            logger.warning(
                f"Database table '{table_name}' does not exist in SQLite."
            )
            return pd.DataFrame()

        df = pd.read_sql(f"SELECT * FROM {table_name}", con=engine)
        logger.info(
            f"Successfully loaded {len(df)} rows from database table: '{table_name}'"
        )
        return df
    except Exception as e:
        logger.error(
            f"Failed to load table '{table_name}' from database: {e}",
            exc_info=True,
        )
        return pd.DataFrame()
from sqlalchemy import create_engine
import pandas as pd
import urllib
import traceback

class ExactSQL:
    """
    Provides a simple interface for connecting to a SQL Server database using
    SQLAlchemy and executing queries. Automatically runs an initial query
    on instantiation and stores the results as a DataFrame.

    *** This is still a work in progress. ***

    Parameters
    ----------
    query : str
        SQL query to execute upon initialization.
    """
    def __init__(self):
        self.driver = urllib.parse.quote_plus("SQL Server")
        try:
            self.engine = create_engine(f"mssql+pyodbc://@be-db-01/200?driver={self.driver}&trusted_connection=yes")
        except Exception as e:
            print("Connection failed!")
            print(e)

        self._query = ""

        self.component_view = "_VH_vw_artikelen"
        self.stocklist_view = "_VH_vw_DS_stocklist"
        self.production_order_view = "_VH_vw_DCL_ProductionOrder"
        self.BOM_header_view = "_VH_vw_DS_BOMHeader"
        self.BOM_lines_view = "_VH_vw_DS_BOMLines"

    @property
    def query(self) -> str:
        return self._query
    
    @query.setter
    def query(self, query: str):
        self._query = query
        self.query_df = self.run_query(query)

    def run_query(self, query: str = None):
        try:
            query_df = pd.read_sql(query, self.engine)
            return query_df
        except Exception as e:
            print("Query failed!")
            traceback.print_exc()
            return None
        
    def select_all_from_table(self, table_name: str):
        try:
            query = f"SELECT * FROM {table_name}"
            df = self.run_query(query)
            return df

        except Exception as e:
            print(f"Failed to retrieve all data from {table_name}!")
            print(e)
            return None
        
    def get_stocklist_table_for_item(self, itemcode_prefix: str) -> pd.DataFrame:
        try:
            query = f"SELECT * FROM {self.stocklist_view} WHERE itemcode LIKE '{itemcode_prefix}%'"
            df = self.run_query(query)
            return df

        except Exception as e:
            traceback.print_exc()
            return None
        
    def get_production_order_for_item(self, itemcode: str) -> pd.DataFrame:
        try:
            query = f"SELECT * FROM {self.production_order_view} WHERE itemcode LIKE '{itemcode}%'"
            df = self.run_query(query)
            return df

        except Exception as e:
            print("Failed to retrieve production order for item!")
            print(e)
            return None
        
    def get_all_items(self):
        try:
            query = "SELECT * FROM _VH_vw_DS_BOMLines WHERE AssemblyItem LIKE '23014%'"
            df = self.run_query(query)
            return df

        except Exception as e:
            print("Failed to retrieve all items!")
            print(e)
            return None
        
    def get_all_tables(self):
        try:
            query = """
            SELECT TABLE_SCHEMA, TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            ORDER BY TABLE_SCHEMA, TABLE_NAME
            """
            df = pd.read_sql(query, self.engine)
            return df
        except Exception as e:
            print("Failed to retrieve table names!")
            print(e)
            return None


if __name__ == "__main__":
    tv_assembly_code = "23014.10.AM-R0-001"

    # query = f"SELECT TOP 100 * FROM Items WHERE IsAssembled = 1 AND Condition = 'A' AND ItemCode = '{tv_assembly_code}'"
    # # query = f"SELECT * FROM _VH_vw_DS_BOMHeader WHERE ItemCode = '{tv_assembly_code}'"
    # bom_query = f"SELECT * FROM _VH_vw_DS_BOMLines WHERE AssemblyItem = '{tv_assembly_code}'"
    # production_query = "SELECT * FROM _AB_tb_ProductionStatus"

    exact_sql = ExactSQL()
    # df = exact_sql.get_stocklist_table_for_item("20025")
    # print(df["itemDescription"].tolist())
    df = exact_sql.get_production_order_for_item("20025")
    print(df.head())
    print(df["Component Number or Value"].tolist())
    print(df.columns.tolist())

    # print(exact_sql.query_df.columns.tolist())
    # tables = exact_sql.get_all_tables()
    # print(tables["TABLE_NAME"].tolist())
    
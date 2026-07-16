
import psycopg2
conn = psycopg2.connect('dbname=postgres user=postgres password=password host=relational_db port=5432')
cur = conn.cursor()
cur.execute('UPDATE llm_provider SET api_base = NULL WHERE id = 1;')
cur.execute('UPDATE model_configuration SET model_name = \'gemini/gemini-flash-lite-latest\' WHERE id = 39;')
conn.commit()
print('SUCCESS!')


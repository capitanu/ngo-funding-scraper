-- Create table
CREATE TABLE funding_state (
  id TEXT PRIMARY KEY DEFAULT 'default',
  applied TEXT[] DEFAULT '{}',
  irrelevant TEXT[] DEFAULT '{}'
);

-- Insert initial row
INSERT INTO funding_state (id) VALUES ('default');

-- Enable public access (for anon key)
ALTER TABLE funding_state ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public access" ON funding_state FOR ALL USING (true) WITH CHECK (true);

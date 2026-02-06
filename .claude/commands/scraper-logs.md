Check recent scraper output for issues:

1. Find the active scraper task output file in `/private/tmp/claude-*/tasks/*.output`
2. Tail last 50 lines
3. Count patterns:
   - "links" = successful queries
   - "No links found" = empty results
   - "error" or "Error" = failures
   - "Warning" = issues

Report summary: X successful, Y empty, Z errors

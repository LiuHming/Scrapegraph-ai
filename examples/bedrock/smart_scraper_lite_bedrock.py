""" 
Basic example of scraping pipeline using SmartScraper
"""
import json
from scrapegraphai.graphs import SmartScraperLiteGraph
from scrapegraphai.utils import prettify_exec_info

graph_config = {
    "llm": {
        "client": "client_name",
        "model": "bedrock/anthropic.claude-3-sonnet-20240229-v1:0",
        "temperature": 0.0
    }
}

smart_scraper_lite_graph = SmartScraperLiteGraph(
    prompt="Who is Marco Perini?",
    source="https://perinim.github.io/",
    config=graph_config
)

result = smart_scraper_lite_graph.run()
print(json.dumps(result, indent=4))

graph_exec_info = smart_scraper_lite_graph.get_execution_info()
print(prettify_exec_info(graph_exec_info))

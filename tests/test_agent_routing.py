import pytest
import pandas as pd
from backend.dataset import clean_and_profile_dataset
from backend.agent import DataAgent
from backend.llm_client import LLMClient
from backend.schemas import ChartSpec

class MockLLMClient(LLMClient):
    def __init__(self, responses):
        super().__init__("fake_key")
        self.responses = responses
        self.call_count = 0
        
    def chat(self, messages, tools=None, tool_choice="auto"):
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp
        
    def generate_json(self, messages, response_format=None):
        return {"blocks": [{"type": "markdown", "text": "Final Answer"}]}

@pytest.fixture
def sample_dataset():
    df = pd.DataFrame({"sales": [10, 20, 30], "region": ["A", "B", "A"]})
    return clean_and_profile_dataset("test", df)

def test_agent_routing(sample_dataset):
    mock_responses = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "statistical_analysis",
                        "arguments": '{"columns": ["sales"]}'
                    }
                }
            ]
        },
        {
            "role": "assistant",
            "content": '{"blocks": [{"type": "markdown", "text": "Final"}]}',
            "tool_calls": []
        }
    ]
    
    agent = DataAgent(MockLLMClient(mock_responses))
    resp, new_tools = agent.run("What is average sales?", sample_dataset, [])
    
    assert len(resp.tool_trace) == 1
    assert resp.tool_trace[0].name == "statistical_analysis"
    assert resp.tool_trace[0].ok == True
    
    assert len(resp.blocks) == 1
    assert resp.blocks[0].type == "markdown"

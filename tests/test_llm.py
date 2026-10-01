import pytest
from unittest.mock import patch, MagicMock
from whatsaid.llm.client import LLMClient
from whatsaid.llm.workflow import create_workflow

@pytest.fixture
def mock_litellm_completion():
    with patch("whatsaid.llm.client.completion") as mock_completion:
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Hello from mock!"))
        ]
        mock_completion.return_value = mock_response
        yield mock_completion

def test_llm_client_generate(mock_litellm_completion):
    client = LLMClient()
    response = client.generate(prompt="Say hello", model="gpt-3.5-turbo")
    
    assert response == "Hello from mock!"
    mock_litellm_completion.assert_called_once()
    args, kwargs = mock_litellm_completion.call_args
    assert kwargs["model"] == "gpt-3.5-turbo"
    assert kwargs["messages"][0]["content"] == "Say hello"

def test_workflow_execution(mock_litellm_completion):
    workflow = create_workflow()
    
    # Run the workflow
    final_state = workflow.invoke({"input_text": "Extract details"})
    
    # We expect the workflow to use the LLM and return a state with an extraction result
    assert "result" in final_state
    assert final_state["result"] == "Hello from mock!"

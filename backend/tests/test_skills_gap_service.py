import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend.services.skills_gap_service import analyze_skills_gap

@pytest.fixture
def mock_jd_text():
    return "Looking for a Python developer with experience in Django, React, and Kubernetes."

@pytest.fixture
def mock_user_profile():
    return "Python developer with experience in Flask and Vue.js."

@pytest.mark.asyncio
async def test_analyze_skills_gap(mock_jd_text, mock_user_profile):
    # Setup mock LLM response with an AI tell
    mock_result = MagicMock()
    # "As an AI" should be stripped, "delve" should be replaced
    mock_result.text = "As an AI, I suggest we delve into the gaps. The candidate is missing Django, React, and Kubernetes."
    mock_call_llm = AsyncMock(return_value=mock_result)

    # Execute
    with patch("backend.services.skills_gap_service.call_llm", new=mock_call_llm):
        result = await analyze_skills_gap(mock_jd_text, mock_user_profile)

    # Verify LLM was called
    mock_call_llm.assert_called_once()

    # Verify the scrubber was applied ("As an AI" is stripped, "delve" -> "explore")
    assert "As an AI" not in result
    assert "delve" not in result
    assert "explore" in result or "I suggest we" in result
    assert "Django, React, and Kubernetes" in result

@pytest.mark.asyncio
async def test_analyze_skills_gap_empty_inputs():
    # Empty inputs should return early without calling the LLM
    result = await analyze_skills_gap("", "")
    assert "Insufficient data" in result

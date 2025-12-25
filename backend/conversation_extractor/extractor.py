"""
Bedrock Extractor - Extract structured information from conversations
"""

import json
from typing import Dict, List

import boto3
from aws_lambda_powertools import Logger

logger = Logger(child=True)


class ConversationExtractor:
    """Extract structured information from conversations using Amazon Bedrock"""
    
    PROMPT_TEMPLATE = """You are an information extraction system.
Extract the following fields from the conversation and return ONLY valid JSON:

Required fields:
- name: Full name of the person (string or null)
- company: Company or organization name (string or null)
- role: Job title or role (string or null)
- contact: Email or phone number (string or null)
- main_topic: Main topic discussed (string or null)
- summary: Brief summary of the conversation (string, max 200 words)

Rules:
1. Return ONLY valid JSON, no markdown, no explanations
2. If information is not present, use null
3. Do NOT guess or infer missing information
4. Use exact quotes from the conversation when available
5. Be conservative - if unsure, use null

Conversation:
{conversation_text}

Return JSON:"""
    
    def __init__(self, model_id: str):
        """
        Initialize extractor
        
        Args:
            model_id: Bedrock model ID (e.g., anthropic.claude-3-5-sonnet-20241022-v2:0)
        """
        self.model_id = model_id
        self.bedrock_client = boto3.client("bedrock-runtime")
        logger.info(f"Initialized Bedrock extractor with model: {model_id}")
    
    def extract(self, messages: Dict) -> Dict:
        """
        Extract information from conversation messages
        
        Args:
            messages: Dictionary of message_id -> message_data
            
        Returns:
            Dictionary with extracted fields
        """
        # Format conversation to text
        conversation_text = self._format_conversation(messages)
        
        logger.info(f"Conversation length: {len(conversation_text)} chars")
        
        # Build prompt
        prompt = self.PROMPT_TEMPLATE.format(conversation_text=conversation_text)
        
        # Call Bedrock
        response = self._invoke_bedrock(prompt)
        
        # Parse and validate response
        extracted_info = self._parse_response(response)
        
        logger.info(f"Extracted info: {json.dumps(extracted_info)}")
        
        return extracted_info
    
    def _format_conversation(self, messages: Dict) -> str:
        """
        Format message map to readable text
        
        Args:
            messages: Dictionary of messages
            
        Returns:
            Formatted conversation string
        """
        if not messages:
            return ""
        
        formatted_messages = []
        
        # Sort messages by create_time if available
        sorted_messages = sorted(
            messages.items(),
            key=lambda x: x[1].get("create_time", 0),
        )
        
        for msg_id, msg in sorted_messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", [])
            
            # Extract text from content
            text_parts = []
            for c in content:
                if isinstance(c, dict):
                    # Handle different content types
                    if "body" in c:
                        text_parts.append(c["body"])
                    elif "text" in c:
                        text_parts.append(c["text"])
            
            if text_parts:
                text = " ".join(text_parts)
                formatted_messages.append(f"{role}: {text}")
        
        return "\n\n".join(formatted_messages)
    
    def _invoke_bedrock(self, prompt: str) -> str:
        """
        Call Bedrock API
        
        Args:
            prompt: Formatted prompt
            
        Returns:
            Model response text
        """
        try:
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1500,
                "temperature": 0.0,  # Deterministic for extraction
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            }
            
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )
            
            # Parse response
            response_body = json.loads(response["body"].read())
            
            # Extract text from Claude response
            content = response_body.get("content", [])
            if content and len(content) > 0:
                return content[0].get("text", "")
            
            raise ValueError("Empty response from Bedrock")
            
        except Exception as e:
            logger.error(f"Bedrock invocation failed: {str(e)}")
            raise
    
    def _parse_response(self, response_text: str) -> Dict:
        """
        Parse and validate Bedrock response
        
        Args:
            response_text: Raw response from model
            
        Returns:
            Validated extracted information
        """
        try:
            # Try to parse JSON
            # Handle markdown code blocks if present
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            extracted = json.loads(response_text.strip())
            
            # Validate required fields
            required_fields = [
                "name",
                "company",
                "role",
                "contact",
                "main_topic",
                "summary",
            ]
            
            validated = {}
            for field in required_fields:
                value = extracted.get(field)
                # Convert empty strings to None
                validated[field] = value if value else None
            
            return validated
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {response_text}")
            logger.error(f"JSON error: {str(e)}")
            # Return empty result
            return {
                "name": None,
                "company": None,
                "role": None,
                "contact": None,
                "main_topic": None,
                "summary": None,
            }

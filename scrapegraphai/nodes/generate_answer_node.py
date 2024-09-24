from typing import List, Optional
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnableParallel
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_aws import ChatBedrock
from langchain_mistralai import ChatMistralAI
from langchain_community.chat_models import ChatOllama
from tqdm import tqdm
from .base_node import BaseNode
from ..utils.output_parser import get_structured_output_parser, get_pydantic_output_parser
from ..prompts import (
    TEMPLATE_CHUNKS, TEMPLATE_NO_CHUNKS, TEMPLATE_MERGE,
    TEMPLATE_CHUNKS_MD, TEMPLATE_NO_CHUNKS_MD, TEMPLATE_MERGE_MD
)

class GenerateAnswerNode(BaseNode):
    def __init__(
        self,
        input: str,
        output: List[str],
        node_config: Optional[dict] = None,
        node_name: str = "GenerateAnswer",
    ):
        super().__init__(node_name, "node", input, output, 2, node_config)
        self.llm_model = node_config["llm_model"]

        if isinstance(node_config["llm_model"], ChatOllama):
            self.llm_model.format = "json"

        self.verbose = node_config.get("verbose", False)
        self.force = node_config.get("force", False)
        self.script_creator = node_config.get("script_creator", False)
        self.is_md_scraper = node_config.get("is_md_scraper", False)
        self.additional_info = node_config.get("additional_info")

    def execute(self, state: dict) -> dict:
        self.logger.info(f"--- Executing {self.node_name} Node ---")

        input_keys = self.get_input_keys(state)
        input_data = [state[key] for key in input_keys]
        user_prompt = input_data[0]
        doc = input_data[1]

        if self.node_config.get("schema", None) is not None:
            if isinstance(self.llm_model, (ChatOpenAI, ChatMistralAI)):
                self.llm_model = self.llm_model.with_structured_output(
                    schema=self.node_config["schema"]
                )
                output_parser = get_structured_output_parser(self.node_config["schema"])
                format_instructions = "NA"
            else:
                if not isinstance(self.llm_model, ChatBedrock):
                    output_parser = get_pydantic_output_parser(self.node_config["schema"])
                    format_instructions = output_parser.get_format_instructions()
                else:
                    output_parser = None
                    format_instructions = ""
        else:
            if not isinstance(self.llm_model, ChatBedrock):
                output_parser = JsonOutputParser()
                format_instructions = output_parser.get_format_instructions()
            else:
                output_parser = None
                format_instructions = ""

        if isinstance(self.llm_model, (ChatOpenAI, AzureChatOpenAI)) \
            and not self.script_creator \
            or self.force \
            and not self.script_creator or self.is_md_scraper:
            template_no_chunks_prompt = TEMPLATE_NO_CHUNKS_MD
            template_chunks_prompt = TEMPLATE_CHUNKS_MD
            template_merge_prompt = TEMPLATE_MERGE_MD
        else:
            template_no_chunks_prompt = TEMPLATE_NO_CHUNKS
            template_chunks_prompt = TEMPLATE_CHUNKS
            template_merge_prompt = TEMPLATE_MERGE

        if self.additional_info is not None:
            template_no_chunks_prompt = self.additional_info + template_no_chunks_prompt
            template_chunks_prompt = self.additional_info + template_chunks_prompt
            template_merge_prompt = self.additional_info + template_merge_prompt

        if len(doc) == 1:
            prompt = PromptTemplate(
                template=template_no_chunks_prompt,
                input_variables=["question"],
                partial_variables={"context": doc, "format_instructions": format_instructions}
            )
            chain = prompt | self.llm_model
            if output_parser:
                chain = chain | output_parser
            answer = chain.invoke({"question": user_prompt})

            state.update({self.output[0]: answer})
            return state

        chains_dict = {}
        for i, chunk in enumerate(tqdm(doc, desc="Processing chunks", disable=not self.verbose)):
            prompt = PromptTemplate(
                template=template_chunks_prompt,
                input_variables=["question"],
                partial_variables={"context": chunk, "chunk_id": i + 1, "format_instructions": format_instructions}
            )
            chain_name = f"chunk{i+1}"
            chains_dict[chain_name] = prompt | self.llm_model
            if output_parser:
                chains_dict[chain_name] = chains_dict[chain_name] | output_parser

        async_runner = RunnableParallel(**chains_dict)
        batch_results = async_runner.invoke({"question": user_prompt})

        merge_prompt = PromptTemplate(
            template=template_merge_prompt,
            input_variables=["context", "question"],
            partial_variables={"format_instructions": format_instructions}
        )

        merge_chain = merge_prompt | self.llm_model
        if output_parser:
            merge_chain = merge_chain | output_parser
        answer = merge_chain.invoke({"context": batch_results, "question": user_prompt})

        state.update({self.output[0]: answer})
        return state

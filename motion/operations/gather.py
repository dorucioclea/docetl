from typing import Dict, List, Tuple
from motion.operations.base import BaseOperation


class GatherOperation(BaseOperation):
    """
    A class that implements a gather operation on input data, adding contextual information from surrounding chunks.

    This class extends BaseOperation to:
    1. Group chunks by their document ID.
    2. Order chunks within each group.
    3. Add peripheral context to each chunk based on the configuration.
    4. Return results containing the formatted chunks with added context, including information about skipped characters.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def syntax_check(self) -> None:
        required_keys = ["content_key", "doc_id_key", "order_key"]
        for key in required_keys:
            if key not in self.config:
                raise ValueError(
                    f"Missing required key '{key}' in GatherOperation configuration"
                )

        if "peripheral_chunks" not in self.config:
            raise ValueError(
                "Missing 'peripheral_chunks' configuration in GatherOperation"
            )

        peripheral_config = self.config["peripheral_chunks"]
        for direction in ["previous", "next"]:
            if direction not in peripheral_config:
                continue
            for section in ["head", "middle", "tail"]:
                if section in peripheral_config[direction]:
                    section_config = peripheral_config[direction][section]
                    if section != "middle" and "count" not in section_config:
                        raise ValueError(
                            f"Missing 'count' in {direction}.{section} configuration"
                        )

        if "main_chunk_start" in self.config and not isinstance(
            self.config["main_chunk_start"], str
        ):
            raise TypeError("'main_chunk_start' must be a string")
        if "main_chunk_end" in self.config and not isinstance(
            self.config["main_chunk_end"], str
        ):
            raise TypeError("'main_chunk_end' must be a string")

    def execute(self, input_data: List[Dict]) -> Tuple[List[Dict], float]:
        content_key = self.config["content_key"]
        doc_id_key = self.config["doc_id_key"]
        order_key = self.config["order_key"]
        peripheral_config = self.config["peripheral_chunks"]
        main_chunk_start = self.config.get(
            "main_chunk_start", "--- Begin Main Chunk ---"
        )
        main_chunk_end = self.config.get("main_chunk_end", "--- End Main Chunk ---")
        results = []
        cost = 0.0

        # Group chunks by document ID
        grouped_chunks = {}
        for item in input_data:
            doc_id = item[doc_id_key]
            if doc_id not in grouped_chunks:
                grouped_chunks[doc_id] = []
            grouped_chunks[doc_id].append(item)

        # Process each group of chunks
        for doc_id, chunks in grouped_chunks.items():
            # Sort chunks by their order within the document
            chunks.sort(key=lambda x: x[order_key])

            # Process each chunk with its peripheral context
            for i, chunk in enumerate(chunks):
                formatted_chunk = self.format_chunk_with_context(
                    chunks,
                    i,
                    peripheral_config,
                    content_key,
                    order_key,
                    main_chunk_start,
                    main_chunk_end,
                )

                result = chunk.copy()
                result[f"{content_key}_formatted"] = formatted_chunk
                results.append(result)

        return results, cost

    def format_chunk_with_context(
        self,
        chunks,
        current_index,
        peripheral_config,
        content_key,
        order_key,
        main_chunk_start,
        main_chunk_end,
    ):
        combined_parts = []

        # Process previous chunks
        combined_parts.append("--- Previous Context ---")
        combined_parts.extend(
            self.process_peripheral_chunks(
                chunks[:current_index],
                peripheral_config.get("previous", {}),
                content_key,
                order_key,
                reverse=True,
            )
        )
        combined_parts.append("--- End Previous Context ---\n")

        # Process main chunk
        main_chunk = chunks[current_index]
        combined_parts.append(
            f"{main_chunk_start}\n{main_chunk[content_key]}\n{main_chunk_end}"
        )

        # Process next chunks
        combined_parts.append("\n--- Next Context ---")
        combined_parts.extend(
            self.process_peripheral_chunks(
                chunks[current_index + 1 :],
                peripheral_config.get("next", {}),
                content_key,
                order_key,
            )
        )
        combined_parts.append("--- End Next Context ---")

        return "\n".join(combined_parts)

    def process_peripheral_chunks(
        self, chunks, config, content_key, order_key, reverse=False
    ):
        if reverse:
            chunks = list(reversed(chunks))

        processed_parts = []
        included_chunks = []
        total_chunks = len(chunks)

        head_config = config.get("head", {})
        tail_config = config.get("tail", {})

        head_count = int(head_config.get("count", 0))
        tail_count = int(tail_config.get("count", 0))
        in_skip = False
        skip_char_count = 0

        for i, chunk in enumerate(chunks):
            if i < head_count:
                section = "head"
            elif i >= total_chunks - tail_count:
                section = "tail"
            elif "middle" in config:
                section = "middle"
            else:
                # Show number of characters skipped
                skipped_chars = sum(len(c[content_key]) for c in chunks)
                if not in_skip:
                    skip_char_count += skipped_chars
                    in_skip = True
                else:
                    skip_char_count += skipped_chars

                continue

            if in_skip:
                processed_parts.append(
                    f"[... {skip_char_count} characters skipped ...]"
                )
                in_skip = False
                skip_char_count = 0

            section_config = config.get(section, {})
            section_content_key = section_config.get("content_key", content_key)

            is_summary = section_content_key != content_key
            summary_suffix = " (Summary)" if is_summary else ""

            chunk_prefix = f"[Chunk {chunk[order_key]}{summary_suffix}]"
            processed_parts.append(f"{chunk_prefix} {chunk[section_content_key]}")
            included_chunks.append(chunk)

        if in_skip:
            processed_parts.append(f"[... {skip_char_count} characters skipped ...]")

        if reverse:
            processed_parts = list(reversed(processed_parts))

        return processed_parts

Task(
    subagent_type="general-purpose",
    description="Extract insights batch {batch_number}/{total_batches}",
    prompt='''
Extract insights from PR review threads (batch {batch_number} of {total_batches}).

Follow: {prompt_file}
Thread IDs: {thread_ids}
Thread count: {thread_count}

Input (threads + batch info): {input_file}
Output: {output_file}
    '''
)

Task(
    subagent_type="general-purpose",
    description="Assign topics to validated insights ({batch_number}/{total_batches})",
    prompt='''
Assign topics to validated insights from mining run (batch {batch_number} of {total_batches}).

Follow: {prompt_file}
Insights file: {insights_file}
Batch input: {input_file} (contains insight IDs for this batch)
Existing topics: {existing_topics}

Output: {output_file}
    '''
)

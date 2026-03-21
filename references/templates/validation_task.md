Task(
    subagent_type="general-purpose",
    description="Validate insights batch {batch_number}/{total_batches}",
    prompt='''
Validate extracted insights against current codebase (batch {batch_number} of {total_batches}).

Follow: {prompt_file}
Insights file: {insights_file}
Insight IDs: {insight_ids}
Insight count: {insight_count}

Input (batch info): {input_file}
Output: {output_file}
    '''
)

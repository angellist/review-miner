Task(
    subagent_type="general-purpose",
    description="Generate review rules for {scope}",
    prompt='''
Generate automated review rules for {scope}.

Follow: {prompt_file}
Library dir: {library_dir} (read *.yaml files where scope = "{scope}")
Target file: {target_file}
Root rules file (for dedup): {root_bugbot_file}

Output: Write the complete {target_file} with selected rules.
    '''
)

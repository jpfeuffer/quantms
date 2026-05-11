process YAML_NORMALIZER {
    tag "$yaml_manifest"
    label 'process_tiny'

    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://depot.galaxyproject.org/singularity/biocontainers/quantms-utils:0.0.25--pyh106432d_0' :
        'biocontainers/quantms-utils:0.0.25--pyh106432d_0' }"

    input:
    path yaml_manifest

    output:
    path "${yaml_manifest.baseName}_openms_design.tsv", emit: ch_expdesign
    path "${yaml_manifest.baseName}_config.tsv"       , emit: ch_yaml_config_file
    path "versions.yml"                              , emit: versions

    script:
    """
    yaml_normalizer.py \\
        "${yaml_manifest}" \\
        --outdir . \\
        --prefix ${yaml_manifest.baseName}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version | awk '{print \$2}')
        pyyaml: \$(python -c 'import yaml; print(yaml.__version__)')
    END_VERSIONS
    """
}

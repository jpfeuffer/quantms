process SPECTRONAUT_LIBRARY_MERGE {
    tag "${experimentName}"
    label 'process_high'
    label 'spectronaut'

    input:
    val experimentName
    path search_archives

    output:
    path '*.kit', emit: library
    path 'versions.yml', emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def archiveArgs = search_archives.collect { "-sa ${it}" }.join(' ')
    def settingsPropArgs = params.spectronaut_settings_prop ? "-s ${params.spectronaut_settings_prop}" : ''
    def settingsJsonArgs = params.spectronaut_settings_json ? "-j ${params.spectronaut_settings_json}" : ''
    def libraryName = "${experimentName}_library.kit"
    """
    # Activate license if key provided via environment variable
    if [ -n "\${SPECTRONAUT_LICENSE_KEY:-}" ]; then
        echo "Activating Spectronaut floating license..."
        spectronaut activate "\$SPECTRONAUT_LICENSE_KEY"
    fi
    
    spectronaut lg -se Pulsar \\
        ${archiveArgs} \\
        -k ${libraryName} \\
        -o . \\
        ${settingsPropArgs} \\
        ${settingsJsonArgs}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spectronaut: \\$(spectronaut -h 2>&1 | head -n 1 | sed 's/^[[:space:]]*//')
    END_VERSIONS
    """

    stub:
    def libraryName = "${experimentName}_library.kit"
    """
    touch ${libraryName}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spectronaut: stub
    END_VERSIONS
    """
}

process SPECTRONAUT_PULSAR_STEP2 {
    tag "${experimentName}"
    label 'process_high'
    label 'spectronaut'

    input:
    val experimentName
    path search_archives

    output:
    path '*.qsp', emit: qsp_file
    path 'versions.yml', emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def archiveArgs = search_archives.collect { "-sa ${it}" }.join(' ')
    def settingsPropArgs = params.spectronaut_settings_prop ? "-rs ${params.spectronaut_settings_prop}" : ''
    def settingsJsonArgs = params.spectronaut_settings_json ? "-j ${params.spectronaut_settings_json}" : ''
    def qspFile = "${experimentName}.qsp"
    """
    # Activate license if key provided via environment variable
    if [ -n "\${SPECTRONAUT_LICENSE_KEY:-}" ]; then
        echo "Activating Spectronaut floating license..."
        spectronaut activate "\$SPECTRONAUT_LICENSE_KEY"
    fi
    
    spectronaut lg -se Pulsar \\
        ${archiveArgs} \\
        -o . \\
        --noOutputSubfolder \\
        ${settingsPropArgs} \\
        ${settingsJsonArgs} \\
        -n "${experimentName}" \\
        --pulsarStage pulsarStep2

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spectronaut: \\$(spectronaut -h 2>&1 | head -n 1 | sed 's/^[[:space:]]*//')
    END_VERSIONS
    """

    stub:
    def qspFile = "${experimentName}.qsp"
    """
    touch ${qspFile}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spectronaut: stub
    END_VERSIONS
    """
}

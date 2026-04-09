# bigbio/quantms: Usage

## :warning: Please read this documentation on the nf-core website: [https://nf-co.re/quantms/usage](https://nf-co.re/quantms/usage)

> _Documentation of pipeline parameters is generated automatically from the pipeline schema and can no longer be found in markdown files._

## Introduction

## Running the pipeline

**Important:** The quantms YAML manifest format is the **approved specification for contract validation** (as defined in `assets/schemas/quantms_yaml_manifest.json`). However, **runtime consumption of YAML manifests is not yet implemented**. The current pipeline accepts **SDRF format** for actual data processing.

This means:

- ✅ The YAML schema is the **official specification** for quantms experiments
- ❌ The pipeline does **NOT yet** read and process `.yml` files end-to-end at runtime
- ✅ You can use the schema to **prepare and validate** YAML manifests in advance
- ✅ Current runtime input remains **SDRF format** (`.sdrf`, `.tsv`, `.csv`)

### Recommended: Prepare YAML Manifests (Current Specification)

Use quantms YAML format to define your entire experiment structure. This specification is stable and ready for adoption:

```bash
# Create and validate your experiment in YAML format
# (Schema validation tools available - see below)
experiment.yml
```

The YAML file should define the following top-level sections:

#### YAML Input Structure (Current Specification)

**`experiment`**: Global experiment settings

- `acquisition_method`: Type of acquisition (e.g., `DDA`, `DIA`)
- `enzyme`: Enzymatic digestion (e.g., `Trypsin`)
- `dissociation_method`: MS/MS fragmentation method (e.g., `HCD`)
- `precursor_mass_tolerance`, `fragment_mass_tolerance`: Mass calibration settings

**`samples`**: Biological samples (one entry per unique biological unit)

- Each sample has a unique `id` and explicit metadata fields like `organism`, `condition`, and `biological_replicate`
- SDRF-derived but less common sample fields should go under `characteristics` and `factor_values`
- Only truly user-specific fields should go under `additional_metadata`
- The validator rejects overlaps between `additional_metadata` and standard sample metadata keys

**`mixtures`**: Multiplex groups (isobaric labeling or SILAC) with channel mappings

- Each mixture has a unique `id` and a `channels` dictionary
- Channel keys (e.g., `TMT126`) map to sample IDs
- For isobaric labeling (TMT, iTRAQ): maps labels to samples
- For SILAC: maps isotope labels to samples

**`runs`**: Raw data files and their assignments

- Each run references a `file` (path or URI)
- `fraction`: optional fraction number (1-based)
- `mixture`: ID of the mixture this run belongs to

**`modifications`**: Merged modification definitions and optional profile grouping

- Each entry defines **one** modification: either ontology-backed (UniMod/MOD) or custom
- Optional `profile` groups modifications into named profiles
- If only one profile is present (or no `profile` is set), it is used by default for all runs
- If multiple profiles are present, runs must select one via `modification_profile`
- Use `kind: ontology` or `kind: custom` to explicitly declare modification type
- For ontology-backed: provide either `ontology_id` (`UNIMOD:<n>` / `MOD:<n>`) or `name`, or both; `accession` remains a deprecated alias
- For ontology-backed modifications, `residues`, `term_specificity`, `mass_shift`, and `formula` are optional dataset-level refinements and are checked against curated ontology values when known
- For custom: provide a friendly `name`, `mass_shift`, and either `residues` or `term_specificity`
- All modifications require `mode: fixed` or `mode: variable`
- Optional `term_specificity` specifies terminal position constraints (`none`, `n-term`, `c-term`, `protein-n-term`, `protein-c-term`)
- Terminal modifications must use `term_specificity`; do not use `N-term` / `C-term` as residues
- Optional tool-specific fields like `binary_group`, `min_occurrences`, `max_occurrences`, `distance_from_terminus`, `localize_mass_shift`, `label_mass_shift`, and `custom_mod_code` live directly on the modification object

#### YAML Example: TMT 16-plex DDA

```yaml
experiment:
  acquisition_method: DDA
  enzyme: Trypsin
  dissociation_method: HCD
  precursor_mass_tolerance: "10 ppm"
  fragment_mass_tolerance: "0.02 Da"

samples:
  - id: treated_rep1
    organism: homo sapiens
    organism_part: cell line
    condition: treated
    biological_replicate: 1

  - id: control_rep1
    organism: homo sapiens
    organism_part: cell line
    condition: control
    biological_replicate: 1

mixtures:
  - id: mix_A
    channels:
      TMT126: treated_rep1
      TMT127N: control_rep1

runs:
  - file: s3://bucket/experiment/mix_A_fraction_1.raw
    fraction: 1
    mixture: mix_A
    modification_profile: phospho_enriched

modifications:
  - profile: default
    kind: ontology
    ontology_id: "UNIMOD:4"
    name: "Carbamidomethyl"
    residues: C
    mode: fixed

  - profile: default
    kind: ontology
    name: "TMT16plex"
    residues: K
    mode: fixed

  - profile: default
    kind: ontology
    name: "TMT16plex"
    term_specificity: n-term
    mode: fixed

  # Ontology-backed modification with flat optional tool-specific fields
  - id: phospho_sty
    profile: phospho_enriched
    kind: ontology
    name: "Phosphorylation"
    ontology_id: "UNIMOD:21"
    residues: [S, T, Y]
    mode: variable # Required enum: fixed|variable
    binary_group: 1
    min_occurrences: 0
    max_occurrences: 3

  # Custom modification without ontology reference
  - id: custom_label
    kind: custom
    name: "My Custom Label"
    residues: K
    mode: fixed
    mass_shift: 138.068
```

The complete schema is defined in: **`assets/schemas/quantms_yaml_manifest.json`**

Refer to the schema for:

- Full field definitions and constraints
- Validation rules for each section
- Optional vs. required fields
- Supported enumeration values (e.g., `acquisition_method` must be `DDA` or `DIA`)

#### YAML Validation

To validate a YAML file against the schema **before** runtime implementation:

```bash
uv run --with jsonschema --with pyyaml python -c "
import json
import yaml
import jsonschema

with open('assets/schemas/quantms_yaml_manifest.json') as f:
    schema = json.load(f)

with open('experiment.yml') as f:
    data = yaml.safe_load(f)

jsonschema.validate(data, schema)
print('✓ Valid quantms YAML manifest')
"
```

Or use the included test suite:

```bash
uv run --with jsonschema --with pyyaml python tests/yaml_contract/test_yaml_input_contract.py
```

#### Timeline and Roadmap

- **Current specification:** Schema definition and validation toolkit available. YAML manifests can be prepared and validated in advance.
- **Future release:** Runtime normalizer/parser implementation (not yet scheduled).
- **Runtime integration not yet implemented:** Full YAML manifest consumption at pipeline runtime.

Until runtime implementation is complete, **use SDRF format for actual pipeline execution** (see below).

### Current Runtime: SDRF Format

### Supported file formats

The pipeline supports the following mass spectrometry data file formats:

- **`.raw`** - Thermo RAW files (automatically converted to mzML)
- **`.mzML`** - Open standard mzML files
- **`.d`** - Bruker timsTOF files (optionally converted to mzML when `--convert_dotd` is set)
- **`.dia`** - DIA-NN native binary format (passed through without conversion)

Compressed variants are supported for `.raw`, `.mzML`, and `.d` formats:

- `.gz` (gzip compressed)
- `.tar` (tar archive)
- `.tar.gz` or `.tgz` (tar gzip compressed)
- `.zip` (zip compressed)

In the respective "comment[file uri]" or "Spectra_Filepath" columns, the mass spectra files to be processed have to be listed. URIs are possible,
and the root folder as well as the file endings can be changed in the options in case of previously downloaded, moved or converted experiments.

This will launch the pipeline with the `docker` configuration profile. See below for more information about profiles.

Note that the pipeline will create the following files in your working directory:

```bash
work                # Directory containing the nextflow working files
<OUTDIR>            # Finished results in specified location (defined with --outdir)
.nextflow_log       # Log file from Nextflow
# Other nextflow hidden files, eg. history of pipeline runs and old logs.
```

If you wish to repeatedly use the same parameters for multiple runs, rather than specifying each flag in the command, you can specify these in a params file.

Pipeline settings can be provided in a `yaml` or `json` file via `-params-file <file>`.

> [!WARNING]
> Do not use `-c <file>` to specify parameters as this will result in errors. Custom config files specified with `-c` must only be used for [tuning process resource specifications](https://nf-co.re/docs/usage/configuration#tuning-workflow-resources), other infrastructural tweaks (such as output directories), or module arguments (args).

The above pipeline run specified with a params file in yaml format:

```bash
nextflow run bigbio/quantms -profile docker -params-file params.yaml
```

with:

```yaml title="params.yaml"
input: './samplesheet.csv'
outdir: './results/'
genome: 'GRCh37'
<...>
```

You can also generate such `YAML`/`JSON` files via [nf-core/launch](https://nf-co.re/launch).

### Updating the pipeline

When you run the above command, Nextflow automatically pulls the pipeline code from GitHub and stores it as a cached version. When running the pipeline after this, it will always use the cached version if available - even if the pipeline has been updated since. To make sure that you're running the latest version of the pipeline, make sure that you regularly update the cached version of the pipeline:

```bash
nextflow pull bigbio/quantms
```

## Migration Guide

### Migrating from luciphor*\* to onsite*\* parameters (Version 1.7.0)

Starting with version 1.7.0, luciphor-specific parameters have been replaced with the unified `onsite_*` parameter naming scheme. The new onsite module supports multiple PTM localization algorithms (AScore, PhosphoRS, and LucXor).

#### Onsite Parameters

| Parameter                        | Default    | Description                                                                                           |
| -------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------- |
| `onsite_algorithm`               | `'lucxor'` | PTM localization algorithm: `'ascore'`, `'phosphors'`, or `'lucxor'`                                  |
| `onsite_fragment_method`         | `'CID'`    | Fragmentation method: `'CID'` or `'HCD'`                                                              |
| `onsite_fragment_tolerance`      | `0.5`      | Fragment mass tolerance                                                                               |
| `onsite_fragment_error_units`    | `'Da'`     | Fragment error units: `'Da'` or `'ppm'`                                                               |
| `onsite_add_decoys`              | `false`    | Add decoy modifications for validation                                                                |
| `onsite_neutral_losses`          | `null`     | List of neutral losses to consider for modification localization (replaces `luciphor_neutral_losses`) |
| `onsite_decoy_mass`              | `null`     | Mass to add to an amino acid to make it a decoy (replaces `luciphor_decoy_mass`)                      |
| `onsite_decoy_neutral_losses`    | `null`     | List of neutral losses for decoy sequences (replaces `luciphor_decoy_neutral_losses`)                 |
| `onsite_threads`                 | `1`        | Number of threads for onsite processing                                                               |
| `onsite_min_psms`                | `5`        | Minimum number of high-scoring PSMs for lucxor model training                                         |
| `onsite_disable_split_by_charge` | `false`    | Disable splitting PSMs by charge state for lucxor                                                     |
| `onsite_compute_all_scores`      | `false`    | Compute all scores for all candidate sites                                                            |

**Note:** The old `luciphor_*` parameters are no longer supported. Update your configuration files to use the `onsite_*` parameters above. The default algorithm is `'lucxor'`, which provides the same functionality as the previous luciphor module.

### Reproducibility

It is a good idea to specify the pipeline version when running the pipeline on your data. This ensures that a specific version of the pipeline code and software are used when you run your pipeline. If you keep using the same tag, you'll be running the same version of the pipeline, even if there have been changes to the code since.

First, go to the [bigbio/quantms releases page](https://github.com/bigbio/quantms/releases) and find the latest pipeline version - numeric only (eg. `1.3.1`). Then specify this when running the pipeline with `-r` (one hyphen) - eg. `-r 1.3.1`. Of course, you can switch to another version by changing the number after the `-r` flag.

This version number will be logged in reports when you run the pipeline, so that you'll know what you used when you look back in the future. For example, at the bottom of the MultiQC reports.

To further assist in reproducibility, you can use share and reuse [parameter files](#running-the-pipeline) to repeat pipeline runs with the same settings without having to write out a command with every single parameter.

> [!TIP]
> If you wish to share such profile (such as upload as supplementary material for academic publications), make sure to NOT include cluster specific paths to files, nor institutional specific profiles.

## Core Nextflow arguments

> [!NOTE]
> These options are part of Nextflow and use a _single_ hyphen (pipeline parameters use a double-hyphen)

### `-profile`

Use this parameter to choose a configuration profile. Profiles can give configuration presets for different compute environments.

Several generic profiles are bundled with the pipeline which instruct the pipeline to use software packaged using different methods (Docker, Singularity, Podman, Shifter, Charliecloud, Apptainer, Conda) - see below.

> [!IMPORTANT]
> We highly recommend the use of Docker or Singularity containers for full pipeline reproducibility, however when this is not possible, Conda is also supported.

The pipeline also dynamically loads configurations from [https://github.com/nf-core/configs](https://github.com/nf-core/configs) when it runs, making multiple config profiles for various institutional clusters available at run time. For more information and to see if your system is available in these configs please see the [nf-core/configs documentation](https://github.com/nf-core/configs#documentation).

Note that multiple profiles can be loaded, for example: `-profile test,docker` - the order of arguments is important!
They are loaded in sequence, so later profiles can overwrite earlier profiles.

If `-profile` is not specified, the pipeline will run locally and expect all software to be installed and available on the `PATH`. This is _not_ recommended, since it can lead to different results on different machines dependent on the computer enviroment.

- `test`
  - A profile with a complete configuration for automated testing
  - Includes links to test data so needs no other parameters
- `docker`
  - A generic configuration profile to be used with [Docker](https://docker.com/)
- `singularity`
  - A generic configuration profile to be used with [Singularity](https://sylabs.io/docs/)
- `podman`
  - A generic configuration profile to be used with [Podman](https://podman.io/)
- `shifter`
  - A generic configuration profile to be used with [Shifter](https://nersc.gitlab.io/development/shifter/how-to-use/)
- `charliecloud`
  - A generic configuration profile to be used with [Charliecloud](https://charliecloud.io/)
- `apptainer`
  - A generic configuration profile to be used with [Apptainer](https://apptainer.org/)
- `wave`
  - A generic configuration profile to enable [Wave](https://seqera.io/wave/) containers. Use together with one of the above (requires Nextflow ` 24.03.0-edge` or later).
- `conda`
  - A generic configuration profile to be used with [Conda](https://conda.io/docs/). Please only use Conda as a last resort i.e. when it's not possible to run the pipeline with Docker, Singularity, Podman, Shifter, Charliecloud, or Apptainer.

### `-resume`

Specify this when restarting a pipeline. Nextflow will use cached results from any pipeline steps where the inputs are the same, continuing from where it got to previously. For input to be considered the same, not only the names must be identical but the files' contents as well. For more info about this parameter, see [this blog post](https://www.nextflow.io/blog/2019/demystifying-nextflow-resume.html).

You can also supply a run name to resume a specific run: `-resume [run-name]`. Use the `nextflow log` command to show previous run names.

### `-c`

Specify the path to a specific config file (this is a core Nextflow command). See the [nf-core website documentation](https://nf-co.re/usage/configuration) for more information.

## Custom configuration

### Resource requests

Each step in the pipeline has a default set of requirements for number of CPUs, memory and time. For most of the steps in the pipeline, if the job exits with an error code of `143` (exceeded requested resources) it will automatically resubmit with higher requests (2 x original, then 3 x original). If it still fails after three times then the pipeline is stopped.

Whilst the default requirements set within the pipeline will hopefully work for most people and with most input data, you may find that you want to customise the compute resources that the pipeline requests. Each step in the pipeline has a default set of requirements for number of CPUs, memory and time. For most of the steps in the pipeline, if the job exits with any of the error codes specified [here](https://github.com/nf-core/rnaseq/blob/4c27ef5610c87db00c3c5a3eed10b1d161abf575/conf/base.config#L18) it will automatically be resubmitted with higher requests (2 x original, then 3 x original). If it still fails after the third attempt then the pipeline execution is stopped.

For example, if the nf-core/rnaseq pipeline is failing after multiple re-submissions of the `STAR_ALIGN` process due to an exit code of `137` this would indicate that there is an out of memory issue:

```console
[62/149eb0] NOTE: Process `NFCORE_RNASEQ:RNASEQ:ALIGN_STAR:STAR_ALIGN (WT_REP1)` terminated with an error exit status (137) -- Execution is retried (1)
Error executing process > 'NFCORE_RNASEQ:RNASEQ:ALIGN_STAR:STAR_ALIGN (WT_REP1)'

Caused by:
    Process `NFCORE_RNASEQ:RNASEQ:ALIGN_STAR:STAR_ALIGN (WT_REP1)` terminated with an error exit status (137)

Command executed:
    STAR \
        --genomeDir star \
        --readFilesIn WT_REP1_trimmed.fq.gz  \
        --runThreadN 2 \
        --outFileNamePrefix WT_REP1. \
        <TRUNCATED>

Command exit status:
    137

Command output:
    (empty)

Command error:
    .command.sh: line 9:  30 Killed    STAR --genomeDir star --readFilesIn WT_REP1_trimmed.fq.gz --runThreadN 2 --outFileNamePrefix WT_REP1. <TRUNCATED>
Work dir:
    /home/pipelinetest/work/9d/172ca5881234073e8d76f2a19c88fb

Tip: you can replicate the issue by changing to the process work dir and entering the command `bash .command.run`
```

#### For beginners

A first step to bypass this error, you could try to increase the amount of CPUs, memory, and time for the whole pipeline. Therefor you can try to increase the resource for the parameters `--max_cpus`, `--max_memory`, and `--max_time`. Based on the error above, you have to increase the amount of memory. Therefore you can go to the [parameter documentation of rnaseq](https://nf-co.re/rnaseq/3.9/parameters) and scroll down to the `show hidden parameter` button to get the default value for `--max_memory`. In this case 128GB, you than can try to run your pipeline again with `--max_memory 200GB -resume` to skip all process, that were already calculated. If you can not increase the resource of the complete pipeline, you can try to adapt the resource for a single process as mentioned below.

#### Advanced option on process level

To bypass this error you would need to find exactly which resources are set by the `STAR_ALIGN` process. The quickest way is to search for `process STAR_ALIGN` in the [nf-core/rnaseq Github repo](https://github.com/nf-core/rnaseq/search?q=process+STAR_ALIGN).
We have standardised the structure of Nextflow DSL2 pipelines such that all module files will be present in the `modules/` directory and so, based on the search results, the file we want is `modules/nf-core/star/align/main.nf`.
If you click on the link to that file you will notice that there is a `label` directive at the top of the module that is set to [`label process_high`](https://github.com/nf-core/rnaseq/blob/4c27ef5610c87db00c3c5a3eed10b1d161abf575/modules/nf-core/software/star/align/main.nf#L9).
The [Nextflow `label`](https://www.nextflow.io/docs/latest/process.html#label) directive allows us to organise workflow processes in separate groups which can be referenced in a configuration file to select and configure subset of processes having similar computing requirements.
The default values for the `process_high` label are set in the pipeline's [`base.config`](https://github.com/nf-core/rnaseq/blob/4c27ef5610c87db00c3c5a3eed10b1d161abf575/conf/base.config#L33-L37) which in this case is defined as 72GB.
Providing you haven't set any other standard nf-core parameters to **cap** the [maximum resources](https://nf-co.re/usage/configuration#max-resources) used by the pipeline then we can try and bypass the `STAR_ALIGN` process failure by creating a custom config file that sets at least 72GB of memory, in this case increased to 100GB.
The custom config below can then be provided to the pipeline via the [`-c`](#-c) parameter as highlighted in previous sections.

```nextflow
process {
    withName: 'NFCORE_RNASEQ:RNASEQ:ALIGN_STAR:STAR_ALIGN' {
        memory = 100.GB
    }
}
```

> **NB:** We specify the full process name i.e. `NFCORE_RNASEQ:RNASEQ:ALIGN_STAR:STAR_ALIGN` in the config file because this takes priority over the short name (`STAR_ALIGN`) and allows existing configuration using the full process name to be correctly overridden.
>
> If you get a warning suggesting that the process selector isn't recognised check that the process name has been specified correctly.

### Updating containers (advanced users)

The [Nextflow DSL2](https://www.nextflow.io/docs/latest/dsl2.html) implementation of this pipeline uses one container per process which makes it much easier to maintain and update software dependencies. If for some reason you need to use a different version of a particular tool with the pipeline then you just need to identify the `process` name and override the Nextflow `container` definition for that process using the `withName` declaration. For example, in the [nf-core/viralrecon](https://nf-co.re/viralrecon) pipeline a tool called [Pangolin](https://github.com/cov-lineages/pangolin) has been used during the COVID-19 pandemic to assign lineages to SARS-CoV-2 genome sequenced samples. Given that the lineage assignments change quite frequently it doesn't make sense to re-release the nf-core/viralrecon everytime a new version of Pangolin has been released. However, you can override the default container used by the pipeline by creating a custom config file and passing it as a command-line argument via `-c custom.config`.

1. Check the default version used by the pipeline in the module file for [Pangolin](https://github.com/nf-core/viralrecon/blob/a85d5969f9025409e3618d6c280ef15ce417df65/modules/nf-core/software/pangolin/main.nf#L14-L19)
2. Find the latest version of the Biocontainer available on [Quay.io](https://quay.io/repository/biocontainers/pangolin?tag=latest&tab=tags)
3. Create the custom config accordingly:

- For Docker:

```nextflow
process {
    withName: PANGOLIN {
        container = 'biocontainers/pangolin:3.0.5--pyhdfd78af_0'
    }
}
```

- For Singularity:

```nextflow
process {
    withName: PANGOLIN {
        container = 'https://depot.galaxyproject.org/singularity/pangolin:3.0.5--pyhdfd78af_0'
    }
}
```

- For Conda:

```nextflow
process {
    withName: PANGOLIN {
        conda = 'bioconda::pangolin=3.0.5'
    }
}
```

> **NB:** If you wish to periodically update individual tool-specific results (e.g. Pangolin) generated by the pipeline then you must ensure to keep the `work/` directory otherwise the `-resume` ability of the pipeline will be compromised and it will restart from scratch.

### nf-core/configs

In most cases, you will only need to create a custom config as a one-off but if you and others within your organisation are likely to be running nf-core pipelines regularly and need to use the same settings regularly it may be a good idea to request that your custom config file is uploaded to the `nf-core/configs` git repository. Before you do this please can you test that the config file works with your pipeline of choice using the `-c` parameter. You can then create a pull request to the `nf-core/configs` repository with the addition of your config file, associated documentation file (see examples in [`nf-core/configs/docs`](https://github.com/nf-core/configs/tree/master/docs)), and amending [`nfcore_custom.config`](https://github.com/nf-core/configs/blob/master/nfcore_custom.config) to include your custom profile.

See the main [Nextflow documentation](https://www.nextflow.io/docs/latest/config.html) for more information about creating your own configuration files.

If you have any questions or issues please send us a message on [Slack](https://nf-co.re/join/slack) on the [`#configs` channel](https://nfcore.slack.com/channels/configs).

## Azure Resource Requests

To be used with the `azurebatch` profile by specifying the `-profile azurebatch`.
We recommend providing a compute `params.vm_type` of `Standard_D16_v3` VMs by default but these options can be changed if required.

Note that the choice of VM size depends on your quota and the overall workload during the analysis.
For a thorough list, please refer the [Azure Sizes for virtual machines in Azure](https://docs.microsoft.com/en-us/azure/virtual-machines/sizes).

## Running in the background

Nextflow handles job submissions and supervises the running jobs. The Nextflow process must run until the pipeline is finished.

The Nextflow `-bg` flag launches Nextflow in the background, detached from your terminal so that the workflow does not stop if you log out of your session. The logs are saved to a file.

Alternatively, you can use `screen` / `tmux` or similar tool to create a detached session which you can log back into at a later time.
Some HPC setups also allow you to run nextflow within a cluster job submitted your job scheduler (from where it submits more jobs).

## Nextflow memory requirements

In some cases, the Nextflow Java virtual machines can start to request a large amount of memory.
We recommend adding the following line to your environment to limit this (typically in `~/.bashrc` or `~./bash_profile`):

```bash
NXF_OPTS='-Xms1g -Xmx4g'
```

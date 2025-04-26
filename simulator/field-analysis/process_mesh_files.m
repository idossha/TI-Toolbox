function process_mesh_files(mesh_dir, varargin)
    % PROCESS_MESH_FILES
    %  Process .msh files in 'mesh_dir' and generate histograms, surfaces, and
    %  summary data.
    %
    % Usage:
    %  process_mesh_files(mesh_dir)
    %  process_mesh_files(mesh_dir, 'debug', true)
    %
    % Optional Name-Value Pair:
    %  'debug': If true, prints extra debugging information to the console.
    %
    % Author: <Your Name>
    % -------------------------------------------------------------------------

    % Parse optional arguments
    p = inputParser;
    addRequired(p, 'mesh_dir', @(x) (ischar(x) || isstring(x)));
    addParameter(p, 'debug', false, @(x) islogical(x) || isnumeric(x));
    parse(p, mesh_dir, varargin{:});
    debug_flag = p.Results.debug;

    % Debug helper
    debug_print = @(msg) fprintf('[DEBUG] %s\n', msg);
    
    if debug_flag
        debug_print(sprintf('Entered process_mesh_files with mesh_dir="%s"', mesh_dir));
    end

    if nargin < 1
        error('You must provide the path to the mesh directory as an argument.');
    end

    % Ensure mesh_dir is valid
    if ~isfolder(mesh_dir)
        error('The specified mesh directory "%s" does not exist.', mesh_dir);
    end

    mesh_files = dir(fullfile(mesh_dir, '*.msh'));
    if debug_flag
        debug_print(sprintf('Found %d .msh files in directory "%s"', length(mesh_files), mesh_dir));
    end

    results_dir = fullfile(mesh_dir, 'results');
    if ~exist(results_dir, 'dir')
        try
            mkdir(results_dir);
            if debug_flag
                debug_print(sprintf('Created results directory "%s"', results_dir));
            end
        catch ME
            error('Failed to create results directory "%s": %s', results_dir, ME.message);
        end
    end

    summary_file = fullfile(results_dir, 'summary.txt');
    summary_fid = fopen(summary_file, 'w');
    if summary_fid == -1
        error('Cannot open summary file "%s" for writing.', summary_file);
    end

    warning('off', 'all');  % Turn off all warnings (you may want to refine this)

    % Main processing loop
    for i = 1:length(mesh_files)
        mesh_file = fullfile(mesh_dir, mesh_files(i).name);
        fprintf('Processing %s\n', mesh_files(i).name);

        % Load the mesh
        try
            if debug_flag
                debug_print(sprintf('Loading mesh file: %s', mesh_file));
            end
            m = mesh_load_gmsh4(mesh_file);
            if debug_flag
                debug_print(sprintf('Mesh loaded successfully. Structure fields:\n%s', evalc('disp(fieldnames(m))')));
            end
        catch ME
            fprintf(2, '[ERROR] Failed to load mesh file "%s": %s\n', mesh_file, ME.message);
            continue;  % Skip to the next file
        end

        % Create histogram
        try
            if debug_flag
                debug_print('Creating histogram figure...');
            end
            fig_histogram = figure('Visible', 'off');
            ax_histogram = axes(fig_histogram);
            mesh_get_histogram(m, 'haxis', ax_histogram);

            if debug_flag
                debug_print('Saving histogram image...');
            end
            save_histogram_image(mesh_files(i).name, fig_histogram, results_dir);

            close(fig_histogram);
        catch ME
            fprintf(2, '[ERROR] Failed to create/save histogram for file "%s": %s\n', mesh_file, ME.message);
        end

        % Compute fieldpeaks and focality
        try
            if debug_flag
                debug_print('Computing field peaks and focality...');
            end
            s = mesh_get_fieldpeaks_and_focality(m, 'printsummary', false);

            if debug_flag
                debug_print('Saving peaks/focality results...');
            end
            save_results(mesh_files(i).name, s, results_dir);

            if debug_flag
                debug_print('Writing summary information to summary.txt...');
            end
            write_summary(summary_fid, mesh_files(i).name, s);
        catch ME
            fprintf(2, '[ERROR] Failed to compute/save field peaks/focality for "%s": %s\n', mesh_file, ME.message);
        end

        % Create surface image
        try
            if debug_flag
                debug_print('Creating surface visualization...');
            end
            fig_surface = figure('Visible', 'off');
            ax_surface = axes(fig_surface);
            mesh_show_surface(m, 'haxis', ax_surface);

            if debug_flag
                debug_print('Saving surface image...');
            end
            save_surface_image(mesh_files(i).name, fig_surface, results_dir);

            close(fig_surface);
        catch ME
            fprintf(2, '[ERROR] Failed to create/save surface image for "%s": %s\n', mesh_file, ME.message);
        end

        if debug_flag
            debug_print(sprintf('Finished processing mesh file: %s', mesh_file));
        end
    end

    fclose(summary_fid);
    warning('on', 'all');

    if debug_flag
        debug_print(sprintf('All files processed. Summary written to: %s', summary_file));
    end
end

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Helper Functions
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

function save_results(filename, s, results_dir)
    [~, name, ~] = fileparts(filename);
    peaks_focality_file = fullfile(results_dir, [name, '_peaks_focality.mat']);
    save(peaks_focality_file, 's');
end

function save_histogram_image(filename, fig, results_dir)
    [~, name, ~] = fileparts(filename);
    histogram_image_file = fullfile(results_dir, [name, '_histogram.png']);
    saveas(fig, histogram_image_file);
end

function save_surface_image(filename, fig, results_dir)
    [~, name, ~] = fileparts(filename);
    surface_image_file = fullfile(results_dir, [name, '_surface.png']);
    saveas(fig, surface_image_file);
end

function write_summary(fid, filename, s)
    fprintf(fid, 'Summary for %s\n', filename);
    fprintf(fid, 'Field Name: %s\n', s.field_name);
    fprintf(fid, 'Region Indices: %s\n', num2str(s.region_idx));
    fprintf(fid, 'Max Value: %f V/m\n', s.max);
    fprintf(fid, 'Percentiles: %s\n', num2str(s.percentiles));
    fprintf(fid, 'Percentile Values: %s V/m\n', num2str(s.perc_values));
    fprintf(fid, 'Focality Cutoffs: %s\n', num2str(s.focality_cutoffs));
    focality_values_cm3 = s.focality_values / 1000;
    fprintf(fid, 'Focality Values: %s (in cubic cm)\n', num2str(focality_values_cm3));
    fprintf(fid, 'XYZ Max: %s\n', mat2str(s.XYZ_max));
    fprintf(fid, 'XYZ Percentiles: %s\n', mat2str(s.XYZ_perc));
    fprintf(fid, 'XYZ Std Percentiles: %s\n', mat2str(s.XYZstd_perc));

    if isfield(s, 'min')
        fprintf(fid, 'Min Value: %f V/m\n', s.min);
        fprintf(fid, 'Negative Percentile Values: %s V/m\n', num2str(s.perc_neg_values));
        focality_neg_values_cm3 = s.focality_neg_values / 1000;
        fprintf(fid, 'Negative Focality Values: %s (in cubic cm)\n', num2str(focality_neg_values_cm3));
        fprintf(fid, 'XYZ Min: %s\n', mat2str(s.XYZ_min));
        fprintf(fid, 'XYZ Negative Percentiles: %s\n', mat2str(s.XYZ_perc_neg));
        fprintf(fid, 'XYZ Std Negative Percentiles: %s\n', mat2str(s.XYZstd_perc_neg));
    end

    fprintf(fid, '---------------------------------------------\n\n');
end

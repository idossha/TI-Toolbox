function process_mesh_files(mesh_dir)
    if nargin < 1
        error('You must provide the path to the mesh directory as an argument.');
    end

    % Ensure mesh_dir is valid
    if ~isfolder(mesh_dir)
        error('The specified mesh directory does not exist.');
    end

    mesh_files = dir(fullfile(mesh_dir, '*.msh'));

    results_dir = fullfile(mesh_dir, 'results');
    if ~exist(results_dir, 'dir')
        mkdir(results_dir);
    end

    summary_file = fullfile(results_dir, 'summary.txt');
    summary_fid = fopen(summary_file, 'w');
    if summary_fid == -1
        error('Cannot open summary file for writing.');
    end

    warning('off', 'all');

    for i = 1:length(mesh_files)
        mesh_file = fullfile(mesh_dir, mesh_files(i).name);
        fprintf('Processing %s\n', mesh_files(i).name);
        m = mesh_load_gmsh4(mesh_file);

        fig_histogram = figure('Visible', 'off');
        ax_histogram = axes(fig_histogram);
        mesh_get_histogram(m, 'haxis', ax_histogram);
        save_histogram_image(mesh_files(i).name, fig_histogram, results_dir);
        close(fig_histogram);

        s = mesh_get_fieldpeaks_and_focality(m, 'printsummary', false);
        save_results(mesh_files(i).name, s, results_dir);
        write_summary(summary_fid, mesh_files(i).name, s);

        fig_surface = figure('Visible', 'off');
        ax_surface = axes(fig_surface);
        mesh_show_surface(m, 'haxis', ax_surface);
        save_surface_image(mesh_files(i).name, fig_surface, results_dir);
        close(fig_surface);
    end

    fclose(summary_fid);
    warning('on', 'all');
end

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

function main(varargin)
    % Create an input parser
    p = inputParser;
    addRequired(p, 'mesh_dir', @ischar);

    % Parse input arguments
    parse(p, varargin{:});

    % Retrieve the mesh directory argument
    mesh_dir = p.Results.mesh_dir;

    % Call the function to process mesh files
    process_mesh_files(mesh_dir);
end

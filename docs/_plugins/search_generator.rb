module Jekyll
  class SearchGenerator < Generator
    safe true
    priority :low

    def generate(site)
      search_file_path = site.source + '/search/search.json'

      # Only generate if file doesn't exist (prevents regeneration loops)
      unless File.exist?(search_file_path)
        search_data = []

        site.pages.each do |page|
          next unless page.ext == '.md' || page.ext == '.html'

          # Skip certain pages that shouldn't be searchable
          next if page.url == '/' # Skip index
          next if page.url.include?('/assets/') # Skip assets

          content = page.content
          title = page.data['title'] || extract_title_from_content(content) || page.url

          # Clean content for search
          clean_content = content.gsub(/<!--.*?-->/m, '') # Remove HTML comments
          clean_content = clean_content.gsub(/\{%.*?%\}/m, '') # Remove Liquid tags
          clean_content = clean_content.gsub(/<[^>]*>/, '') # Remove HTML tags
          clean_content = clean_content.gsub(/\s+/, ' ') # Normalize whitespace
          clean_content = clean_content.strip

          search_data << {
            'title' => title,
            'content' => clean_content,
            'url' => '/TI-Toolbox' + page.url
          }
        end

        # Write search data to JSON file in source directory
        search_file = File.new(search_file_path, 'w')
        search_file.puts JSON.pretty_generate(search_data)
        search_file.close
      end
    end

    private

    def extract_title_from_content(content)
      # Try to extract title from first heading
      match = content.match(/^#\s+(.+)$/m)
      match ? match[1].strip : nil
    end
  end
end

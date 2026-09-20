require 'json'

module Jekyll
  class SearchGenerator < Generator
    safe true
    priority :lowest

    def generate(site)
      search_data = site.pages.map do |page|
        next unless page.ext == '.md' || page.ext == '.html'
        next if page.data['search'] == false
        next if page.data['redirect_generated']
        next if page.url == '/'
        next if page.url.include?('/assets/')

        content = page.content
        title = page.data['title'] || extract_title_from_content(content) || page.url

        # Strip markup that is useful for rendering but noisy in a search snippet.
        clean_content = content.gsub(/<!--.*?-->/m, '')
        clean_content = clean_content.gsub(/\{%.*?%\}/m, '')
        clean_content = clean_content.gsub(/\$\$.*?\$\$/m, ' ')
        clean_content = clean_content.gsub(/<[^>]*>/, '')
        clean_content = clean_content.gsub(/\s+/, ' ').strip

        {
          'title' => title,
          'content' => clean_content,
          'url' => '/TI-Toolbox' + page.url
        }
      end.compact

      search_page = PageWithoutAFile.new(site, site.source, 'search', 'search.json')
      search_page.content = JSON.pretty_generate(search_data) + "\n"
      search_page.data['layout'] = nil
      search_page.data['search'] = false
      search_page.data['sitemap'] = false
      site.pages << search_page
    end

    private

    def extract_title_from_content(content)
      match = content.match(/^#\s+(.+)$/m)
      match ? match[1].strip : nil
    end
  end
end

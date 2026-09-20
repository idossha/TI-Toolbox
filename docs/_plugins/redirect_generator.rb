require 'cgi'
require 'set'

module Jekyll
  class RedirectGenerator < Generator
    safe true
    priority :low

    def generate(site)
      redirects = site.data['redirects'] || []
      authored_urls = site.pages.map(&:url).to_set
      generated_urls = Set.new

      redirects.each do |entry|
        source = entry.fetch('from')
        target = entry.fetch('to')
        validate_route!(source, 'source')
        validate_route!(target, 'target')

        raise ArgumentError, "duplicate redirect source: #{source}" unless generated_urls.add?(source)
        raise ArgumentError, "redirect collides with authored page: #{source}" if authored_urls.include?(source)

        page = redirect_page(site, source, target)
        site.pages << page
      end
    end

    private

    def validate_route!(route, label)
      unless route.is_a?(String) && route.start_with?('/') && !route.start_with?('//') && !route.include?('://')
        raise ArgumentError, "redirect #{label} must be a local absolute route: #{route.inspect}"
      end
    end

    def redirect_page(site, source, target)
      relative_source = source.delete_prefix('/')
      if source.end_with?('/')
        dir = relative_source.delete_suffix('/')
        name = 'index.html'
      else
        dir = File.dirname(relative_source)
        dir = '' if dir == '.'
        name = File.basename(relative_source)
      end

      destination = "#{site.config['baseurl']}#{target}"
      canonical = "#{site.config['url']}#{destination}"
      escaped_destination = CGI.escapeHTML(destination)
      escaped_canonical = CGI.escapeHTML(canonical)

      page = PageWithoutAFile.new(site, site.source, dir, name)
      page.data['layout'] = nil
      page.data['permalink'] = source
      page.data['search'] = false
      page.data['sitemap'] = false
      page.data['redirect_generated'] = true
      page.content = <<~HTML
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8">
            <meta http-equiv="refresh" content="0; url=#{escaped_destination}">
            <link rel="canonical" href="#{escaped_canonical}">
            <title>Page moved</title>
          </head>
          <body>
            <p>This page moved to <a href="#{escaped_destination}">#{escaped_destination}</a>.</p>
          </body>
        </html>
      HTML
      page
    end
  end
end

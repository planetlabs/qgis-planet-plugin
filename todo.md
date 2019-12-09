
### leasot post output

```
~/qgis-planet-explorer-plugin/planet_explorer
$ leasot '**/*.py' --reporter markdown
```

  1. regex find: `\| ([^.]+\.py)( \| )(\d+)`

  2. replace: `| [$1:$3](+++/$1#L$3)`

  3. replace: `+++` with https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer

  4. condense `Filename | line #` to `Filename:line#`

  5. remove middle column header line


### TODOs
| Filename:line# | TODO
|:------|:------
| [pe_utils.py:212](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/pe_utils.py#L212) | Extend to include ALL GeoJSON properties
| [pe_utils.py:446](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/pe_utils.py#L446) | Have to update CRS, too, or new thumbs will have previous one's
| [gui/pe_aoi_maptools.py:232](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_aoi_maptools.py#L232) | validate geom before firing signal
| [gui/pe_dockwidget.py:140](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_dockwidget.py#L140) | This needs a more general, non-temporal link
| [gui/pe_dockwidget.py:466](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_dockwidget.py#L466) | Validate filters
| [gui/pe_dockwidget.py:483](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_dockwidget.py#L483) | Also validate GeoJSON prior to performing search
| [gui/pe_dockwidget.py:489](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_dockwidget.py#L489) | replace hardcoded item type with dynamic item types
| [gui/pe_dockwidget.py:521](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_dockwidget.py#L521) | Add mosacis search
| [gui/pe_dockwidget.py:628](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_dockwidget.py#L628) | Once checked IDs are avaiable
| [gui/pe_dockwidget.py:646](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_dockwidget.py#L646) | Once checked IDs are avaiable
| [gui/pe_dockwidget.py:809](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_dockwidget.py#L809) | Fix signal-triggered collection of filters
| [gui/pe_dockwidget.py:887](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_dockwidget.py#L887) | Template terms.html first section, per subscription level
| [gui/pe_filters.py:276](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_filters.py#L276) | Validate GeoJSON; try planet.api.utils.probably_geojson()
| [gui/pe_filters.py:532](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_filters.py#L532) | validate geom is less than 500 vertices
| [gui/pe_filters.py:741](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_filters.py#L741) | gather existing validation logic here
| [gui/pe_filters.py:742](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_filters.py#L742) | Check for valid json.loads
| [gui/pe_filters.py:744](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_filters.py#L744) | Check API verticie limit of 500
| [gui/pe_filters.py:893](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_filters.py#L893) | (Eventually) Add multi-date range widget with and/or selector
| [gui/pe_filters.py:937](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_filters.py#L937) | (Eventually) Add multi-field searching, with +/- operation
| [gui/pe_filters.py:942](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_filters.py#L942) | Figure out how area coverage filter works in Explorer
| [gui/pe_filters.py:944](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_filters.py#L944) | Consolidate range filters for basemap/mosaic reusability
| [gui/pe_filters.py:1064](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_filters.py#L1064) | Add rest of range sliders
| [gui/pe_filters.py:1139](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_filters.py#L1139) | double check actual domain/range of sliders
| [gui/pe_orders_v2.py:677](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_orders_v2.py#L677) | Add more checks?
| [gui/pe_orders_v2.py:810](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_orders_v2.py#L810) | Grab responseTimeOut from plugin settings and override default
| [gui/pe_orders_v2.py:1021](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_orders_v2.py#L1021) | Add the error reason
| [gui/pe_orders_v2.py:1138](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_orders_v2.py#L1138) | Warn user they will lose any order IDs if they close log
| [gui/pe_search_results.py:248](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_search_results.py#L248) | Style these, too?
| [gui/pe_search_results.py:307](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_search_results.py#L307) | Figure out way of having checkbox not drawn, but still
| [gui/pe_search_results.py:521](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_search_results.py#L521) | Resolve geometry by node_type or do that under node.geometry()?
| [gui/pe_search_results.py:526](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_search_results.py#L526) | Add node
| [gui/pe_search_results.py:554](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_search_results.py#L554) | Add node id, properties as fields?
| [gui/pe_search_results.py:1061](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_search_results.py#L1061) | Clean up model?
| [gui/pe_search_results.py:1090](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_search_results.py#L1090) | Grab responseTimeOut from plugin settings and override default
| [gui/pe_thumbnails.py:471](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/gui/pe_thumbnails.py#L471) | Composite (centered) over top of full width/height
| [planet_api/p_bundles.py:232](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_bundles.py#L232) | Remove "udm and udm2" filter once that's vetted
| [planet_api/p_client.py:109](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_client.py#L109) | add client_v2 when available
| [planet_api/p_client.py:143](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_client.py#L143) | Sanitize?
| [planet_api/p_client.py:147](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_client.py#L147) | swap with new auth endpoint?
| [planet_api/p_client.py:367](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_client.py#L367) | Catch errors
| [planet_api/p_client.py:368](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_client.py#L368) | Switch to async call
| [planet_api/p_models.py:117](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_models.py#L117) | Make this default a user setting as well
| [planet_api/p_models.py:256](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_models.py#L256) | Validate request object
| [planet_api/p_models.py:265](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_models.py#L265) | Add search for mosaics or series
| [planet_api/p_models.py:281](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_models.py#L281) | Turn this into a user message and self-delete results tab
| [planet_api/p_models.py:322](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_models.py#L322) | Catch errors
| [planet_api/p_models.py:362](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_models.py#L362) | Parse nodes, then build up AOI scene parents, for Daily Imagery
| [planet_api/p_models.py:399](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_models.py#L399) | Mosaic quads lazy load thumbnails, or on view expanded()?
| [planet_api/p_models.py:417](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_models.py#L417) | Do without copying anything, i.e. refs from flat results list
| [planet_api/p_models.py:451](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_models.py#L451) | combine geometries for % area coverage of AOI for scene
| [planet_api/p_network.py:220](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_network.py#L220) | Adapt this older approach (callback as instance method does not work,
| [planet_api/p_node.py:379](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_node.py#L379) | Implement mosaics node resource loading
| [planet_api/p_node.py:390](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_node.py#L390) | Add converted date/time to sor_date time zone using pytz
| [planet_api/p_node.py:437](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_node.py#L437) | Add test for mosaics types
| [planet_api/p_thumnails.py:231](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_thumnails.py#L231) | Raise an exception?
| [planet_api/p_thumnails.py:243](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_thumnails.py#L243) | Let things ride for caller, or return some fetching state?
| [planet_api/p_thumnails.py:296](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_thumnails.py#L296) | Pass item_resource instead, to get geometry, etc.
| [planet_api/p_thumnails.py:442](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_thumnails.py#L442) | Figure out all possibly thrown exceptions
| [planet_api/p_thumnails.py:571](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_thumnails.py#L571) | Raise an exception?
| [planet_api/p_thumnails.py:589](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_thumnails.py#L589) | Let things ride for caller, or return some fetching state?
| [tests/test_organize_daily.py:59](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/tests/test_organize_daily.py#L59) | Do this without copying anything, i.e. refs from flat results list
| [tests/test_organize_daily.py:89](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/tests/test_organize_daily.py#L89) | combine geometries for % area coverage of AOI for scene
| [tests/test_thumbnail_cache.py:105](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/tests/test_thumbnail_cache.py#L105) | Pull from settings

### FIXMEs
| Filename:line# | FIXME
|:------|:------
| [pe_utils.py:489](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/pe_utils.py#L489) | Save this to a uuid.gpkg file in user-defined dir or project dir
| [planet_api/p_bundles.py:238](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_bundles.py#L238) | Supposed to have 'and not deprecated' in conditional
| [planet_api/p_client.py:487](https://github.com/planetfederal/qgis-planet-explorer-plugin/blob/master/planet_explorer/planet_api/p_client.py#L487) | Should be using the above code, not direct call to requests

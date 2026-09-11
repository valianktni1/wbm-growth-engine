<?php
/**
 * Plugin Name: WBM Website Insights
 * Description: Consent-controlled public-page measurements for your self-hosted WBM Growth Engine.
 * Version: 1.1.0
 * Requires at least: 6.0
 * Requires PHP: 7.4
 * Author: Weddings By Mark
 */
if (!defined('ABSPATH')) { exit; }
add_action('admin_menu', function () {
    add_options_page('WBM Website Insights', 'WBM Website Insights', 'manage_options', 'wbm-website-insights', 'wbmwi_settings_page');
});
add_filter('plugin_action_links_' . plugin_basename(__FILE__), function ($links) {
    array_unshift($links, '<a href="' . esc_url(admin_url('options-general.php?page=wbm-website-insights')) . '">Settings</a>');
    return $links;
});
add_action('admin_init', function () {
    register_setting('wbmwi', 'wbmwi_options', array('sanitize_callback' => 'wbmwi_sanitize', 'type' => 'array'));
});
function wbmwi_sanitize($raw) {
    if (!is_array($raw)) { return array(); }
    $endpoint = rtrim(esc_url_raw($raw['endpoint'] ?? ''), '/');
    if ($endpoint !== 'https://growth.weddingsbymark.uk') {
        add_settings_error('wbmwi', 'endpoint', 'Use https://growth.weddingsbymark.uk as the Growth address.');
        $endpoint = '';
    }
    $token = sanitize_text_field($raw['token'] ?? '');
    if (!preg_match('/^[A-Za-z0-9_-]{20,80}$/', $token)) { $token = ''; }
    return array('endpoint' => $endpoint, 'token' => $token,
        'enabled' => !empty($raw['enabled']) && $endpoint && $token,
        'own_prompt' => !empty($raw['own_prompt']),
        'form_selector' => substr(sanitize_text_field($raw['form_selector'] ?? ''), 0, 200));
}
function wbmwi_settings_page() {
    if (!current_user_can('manage_options')) { return; }
    $o = get_option('wbmwi_options', array());
    ?><div class="wrap"><h1>WBM Website Insights</h1><p>Measure consenting visits to the public pages selected in Growth. Logged-in WordPress users, previews, feeds and password-protected posts are excluded.</p>
    <form method="post" action="options.php"><?php settings_fields('wbmwi'); ?>
    <table class="form-table"><tr><th>Growth address</th><td><input type="url" class="regular-text" name="wbmwi_options[endpoint]" value="<?php echo esc_attr($o['endpoint'] ?? 'https://growth.weddingsbymark.uk'); ?>"></td></tr>
    <tr><th>Website code</th><td><input class="regular-text" name="wbmwi_options[token]" value="<?php echo esc_attr($o['token'] ?? ''); ?>"><p>Copy from Growth → Website performance → Connect &amp; manage. Never use a Booking key here.</p></td></tr>
    <tr><th>Collection</th><td><label><input type="checkbox" name="wbmwi_options[enabled]" value="1" <?php checked(!empty($o['enabled'])); ?>> Enable website insights</label></td></tr>
    <tr><th>Visitor choice</th><td><label><input type="checkbox" name="wbmwi_options[own_prompt]" value="1" <?php checked($o['own_prompt'] ?? true); ?>> Show this plugin’s Allow / No thanks prompt</label><p>If using an existing consent banner, untick this only after connecting its accept and withdrawal callbacks to <code>window.wbmAnalyticsConsent(true/false)</code>. Without a consent signal, collection stays off. Avoid showing two prompts.</p></td></tr>
    <tr><th>Enquiry form selector (optional)</th><td><input class="regular-text" name="wbmwi_options[form_selector]" value="<?php echo esc_attr($o['form_selector'] ?? ''); ?>"><p>Leave blank until your enquiry form has been checked. A matching form’s first interaction records a start. A successful submission needs a confirmed success hook; a submit-button click is never enough.</p></td></tr></table>
    <?php submit_button(); ?></form><p>Collection begins after consent. No form values, names, email addresses or requested wedding dates are sent. Visits use a random ID in session storage, expiring after 30 minutes of inactivity. Events are kept in Growth for 90 days. Update your website privacy information to describe this before enabling.</p></div><?php
}
add_action('wp_enqueue_scripts', function () {
    $o = get_option('wbmwi_options', array());
    if (empty($o['enabled']) || empty($o['endpoint']) || empty($o['token']) || is_user_logged_in() || is_preview() || is_feed() || is_404() || post_password_required()) { return; }
    wp_enqueue_script('wbm-website-insights', plugin_dir_url(__FILE__) . 'tracker.js', array(), '1.1.0', true);
    wp_enqueue_style('wbm-website-insights', plugin_dir_url(__FILE__) . 'tracker.css', array(), '1.1.0');
    wp_add_inline_script('wbm-website-insights', 'window.wbmInsightsConfig = ' . wp_json_encode(array('endpoint' => $o['endpoint'], 'token' => $o['token'], 'ownPrompt' => !empty($o['own_prompt']), 'formSelector' => $o['form_selector'] ?? '')) . ';', 'before');
});

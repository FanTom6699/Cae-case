$json = Get-Content cards.json -Raw | ConvertFrom-Json
$prices = @{
    'toyota_camry' = 25000
    'honda_civic' = 23000
    'ford_focus' = 21000
    'volkswagen_golf' = 24000
    'hyundai_solaris' = 12000
    'kia_rio' = 15000
    'lada_vesta' = 9000
    'lada_granta' = 7000
    'uaz_patriot' = 18000
    'vaz_2101' = 1000
    'vaz_2106' = 1500
    'vaz_2107' = 2000
    'moskvich_412' = 800
    'gaz_24_volga' = 3000
    'mazda_3' = 21000
    'subaru_impreza' = 22000
    'toyota_corolla' = 23000
    'nissan_altima' = 26000
    'mitsubishi_lancer' = 20000
    'chevrolet_cruze' = 19000
    'bmw_3_series' = 45000
    'mercedes_c_class' = 41000
    'audi_a4' = 40000
    'volkswagen_passat' = 28000
    'skoda_superb' = 35000
    'hyundai_sonata' = 32000
    'kia_optima' = 30000
    'honda_accord' = 33000
    'toyota_camry_new' = 35000
    'nissan_maxima' = 37000
    'mazda_6' = 33000
    'subaru_legacy' = 32000
    'volvo_s60' = 40000
    'jaguar_xe' = 42000
    'infiniti_q50' = 44000
    'acura_tlx' = 39000
    'lexus_is' = 43000
    'bmw_5_series' = 54000
    'mercedes_e_class' = 57000
    'audi_a6' = 55000
    'porsche_911' = 100000
    'lamborghini_huracan' = 240000
    'ferrari_sf90' = 400000
    'mclaren_720s' = 315000
    'bugatti_divo' = 5000000
    'pagani_huayra' = 1400000
    'koenigsegg_jesko' = 3000000
    'ssc_tuatara' = 1750000
    'hennessey_venom_f5' = 1900000
    'aspark_owl' = 3200000
    'rimac_concept_two' = 2400000
    'lotus_evija' = 2300000
    'pininfarina_battista' = 2200000
    'dodge_viper' = 65000
    'chevrolet_corvette_c8' = 60000
    'nissan_gt_r' = 115000
    'toyota_supra' = 55000
    'subaru_wrx_sti' = 42000
    'mitsubishi_lancer_evo' = 60000
    'honda_nsx' = 160000
    'bugatti_chiron' = 2600000
    'lamborghini_veneno' = 4500000
    'ferrari_la_ferrari' = 1400000
    'mclaren_f1' = 15000000
    'pagani_zonda' = 1200000
    'koenigsegg_one_1' = 1850000
    'hennessey_venom_gt' = 1200000
    'koenigsegg_agera_rs' = 1600000
    '9ff_gt9' = 580000
    'gumpert_apollo' = 450000
    'scc_ultimate_aero' = 660000
    'zenvo_st1' = 1225000
    'lykan_hypersport' = 3400000
    'ferrari_250_gto' = 35000000
    'bugatti_type_57' = 8000000
    'maybach_exelero' = 8000000
    'rolls_royce_phantom' = 450000
    'bentley_continental' = 230000
    'mercedes_amg_gt_r' = 165000
    'porsche_918_spyder' = 940000
    'mclaren_p1' = 1350000
}

foreach($key in $prices.Keys) {
    if($json.$key) {
        $json.$key.sell_price = $prices[$key]
    }
}

$json | ConvertTo-Json -Depth 10 | Set-Content cards.json
Write-Host 'Цены обновлены!'

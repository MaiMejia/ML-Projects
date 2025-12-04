### Machine Learning Projects
This repository showcases ML projects I have developed across different domains.

#### 1. Classification 
A fast‑growing logistics startup was struggling to keep customers satisfied despite repeated efforts to identify improvements. To address this, I set up a machine learning model to predict whether customers were happy or unhappy with delivery services. I tested several approaches, including PCA, Random Forest, and other boosting methods, and found that AdaBoost delivered the best performance with 73% accuracy. While further data will be needed to push accuracy higher, this result provided actionable insights and measurable gains in understanding customer satisfaction, helping the company take initial steps toward improving service quality.
<br>_[View Classification Code](classification/CustomerSatisfaction.ipynb)_

#### 2. Prediction
A small startup in the European banking market was seeking to improve customer call success rates by leveraging call center data. The task was to design a machine learning system that could predict whether a customer would subscribe to a term deposit. I explored multiple approaches and developed an evolving product focused on both performance and interpretability, ultimately building an XGBoost model. This model achieved a recall of 88% for detecting positive subscriptions and showed consistent classification across features, providing strong predictive power and actionable insights to help clients make more informed decisions.
<br>_[View Prediction Code](prediction/Predicting_Subscription.ipynb)_

#### 3. NLP 
A talent sourcing company needed a way to efficiently match candidates to tech openings, but struggled with understanding roles, defining required skills, and reaching the best job seekers. I set out to automate the process by predicting candidate fit from available information. I tested several approaches and found that a TF‑DFI model with exact keyword matching produced the strongest rankings, while neural methods like CBOW and Skip‑Gram did not improve results. Filtering by score thresholds helped refine matches depending on job title frequency, and fuzzy matching was identified as a useful mitigation for vocabulary or spelling bias. The model delivered better candidate rankings and provided a scalable path to connect with top performers more effectively.
<br>_[View NLP Code](nlp/Potential_Talents.ipynb)_

#### 4. CNN 
Traditional methods of detecting Malaria are time-consuming, require specialized expertise, and are labor-intensive. This is not an efficient process, which represents a high burden for the healthcare industry and increases the risk of misdiagnosis, which can be fatal. Deep Learning techniques, particularly CNNs, offer a more effective solution to handle this type of challenges.
<br>_[View CNN Code](cnn/ComputerVision.ipynb)_

#### 5. Trading Bot 

<br>_[View Trading Bot Code](ml-tradingbot/btc_bot.py)_

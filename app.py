# -*- coding: utf-8 -*-

from scripts import tabledef
from scripts import forms
from scripts import helpers
from flask import Flask, redirect, url_for, render_template, request, session
import json
import sys
import os
import stripe
import pandas as pd
from werkzeug.utils import secure_filename
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import Ridge
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline


app = Flask(__name__)
app.secret_key = os.urandom(12)  # Generic key for dev purposes only

stripe_keys = {
  'secret_key': 'sk_test_Q1X3Yy6hrqg6IlhkyxO6fWOK002uFyPxuz', # os.environ['STRIPE_SECRET_KEY'],
  'publishable_key': 'pk_test_IWI8wJRf91XYwLjJuw3UWUbw00dF0HjHVm' # os.environ['STRIPE_PUBLISHABLE_KEY']
}

stripe.api_key = stripe_keys['secret_key']

# Heroku
#from flask_heroku import Heroku
#heroku = Heroku(app)

# ======== Routing =========================================================== #
# -------- Login ------------------------------------------------------------- #
@app.route('/', methods=['GET', 'POST'])
def login():
    if not session.get('logged_in'):
        form = forms.LoginForm(request.form)
        if request.method == 'POST':
            username = request.form['username'].lower()
            password = request.form['password']
            if form.validate():
                if helpers.credentials_valid(username, password):
                    session['logged_in'] = True
                    session['username'] = username
                    return json.dumps({'status': 'Login successful'})
                return json.dumps({'status': 'Invalid user/pass'})
            return json.dumps({'status': 'Both fields required'})
        return render_template('login.html', form=form)
    user = helpers.get_user()
    user.active = user.payment == helpers.payment_token()
    user.key = stripe_keys['publishable_key']
    return render_template('home.html', user=user)

# -------- Signup ---------------------------------------------------------- #
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if not session.get('logged_in'):
        form = forms.LoginForm(request.form)
        if request.method == 'POST':
            username = request.form['username'].lower()
            password = helpers.hash_password(request.form['password'])
            email = request.form['email']
            if form.validate():
                if not helpers.username_taken(username):
                    helpers.add_user(username, password, email)
                    session['logged_in'] = True
                    session['username'] = username
                    return json.dumps({'status': 'Signup successful'})
                return json.dumps({'status': 'Username taken'})
            return json.dumps({'status': 'User/Pass required'})
        return render_template('login.html', form=form)
    return redirect(url_for('login'))


# -------- Settings ---------------------------------------------------------- #
@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if session.get('logged_in'):
        if request.method == 'POST':
            password = request.form['password']
            if password != "":
                password = helpers.hash_password(password)
            email = request.form['email']
            helpers.change_user(password=password, email=email)
            return json.dumps({'status': 'Saved'})
        user = helpers.get_user()
        return render_template('settings.html', user=user)
    return redirect(url_for('login'))

# -------- Charge ---------------------------------------------------------- #
@app.route('/charge', methods=['POST'])
def charge():
    if session.get('logged_in'):
        user = helpers.get_user()
        try:
            amount = 1000   # amount in cents
            customer = stripe.Customer.create(
                email= user.email,
                source=request.form['stripeToken']
            )
            stripe.Charge.create(
                customer=customer.id,
                amount=amount,
                currency='usd',
                description='Discount Optimizer Charge'
            )
            helpers.change_user(payment=helpers.payment_token())
            user.active = True
            return render_template('home.html', user=user)
        except stripe.error.StripeError:
            return render_template('error.html')

@app.route("/logout")
def logout():
    session['logged_in'] = False
    return redirect(url_for('login'))

@app.route('/predict', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        f = request.files['file']

        basepath = os.path.dirname(__file__)
        file_path = os.path.join(
            basepath, 'uploads', secure_filename(f.filename))
        f.save(file_path)

        df = pd.read_csv(file_path)
        df = df[df['Qty. Sold'] != 0]
        df = df[df['Discount'] >= 0]
        df['dperi'] = df['Discount']/df['Qty. Sold']
        df['dperi'] = df.dperi.astype(int)

        df.set_index('dperi', inplace=True)
        df.sort_index(inplace=True)
        Y = df[["Profit"]]
        Y_train, Y_test = train_test_split(Y, test_size=0.13, random_state=42)
        X_train = Y_train.index.values.reshape(-1, 1)
        X_test = Y_test.index.values.reshape(-1, 1)

        polymodel = make_pipeline(PolynomialFeatures(5), Ridge())
        polymodel.fit(X_train, Y_train)
        Y_test_pred = polymodel.predict(df.index.values.reshape(-1, 1))
        df['res2'] = Y_test_pred[:,0]
        df['res2'] = df.res2.astype(int)
       
        return "best discount is " + str(df['res2'].idxmax()) + " with planned profit " + str(df.loc[str(df['res2'].idxmax())]["Profit"])
    return None

# ======== Main ============================================================== #
if __name__ == "__main__":
    app.run(debug=True, use_reloader=True)
